import time

import pandas as pd
import streamlit as st

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import StaleElementReferenceException


###############################################################################
# CONFIGURACIÓN GENERAL
###############################################################################

st.set_page_config(
    page_title="Pregunteitor + Respondeitor",
    page_icon="📚"
)

st.title("📚 Pregunteitor + 🎓 Respondeitor")


# ---------------------------------------------------------------------------
# Pregunteitor
# ---------------------------------------------------------------------------

N_TOPICS_TEST = 99
CSV_OPTIONS = [f"topics_{i}.csv" for i in range(1, 11)]


# ---------------------------------------------------------------------------
# Respondeitor
# ---------------------------------------------------------------------------

LOGIN_URL = "https://www.dynamed.com"
AVAILABLE_CREDITS_URL = "https://www.dynamed.com/cme/available-credits"

PAGE_TIMEOUT = 60

OTHER_TEXT = "Other"

NOT_FOUND_TEXT = (
    "I did not find that the information answered my clinical question"
)

MAX_PARTS = 10
MAX_CREDITS = 200


###############################################################################
# SELECCIÓN DE CSV
###############################################################################

TOPICS_FILE = st.selectbox(
    "Selecciona el archivo de topics a usar",
    CSV_OPTIONS
)


###############################################################################
# CARGAR CSV
###############################################################################

try:
    df = pd.read_csv(
        TOPICS_FILE,
        sep=";",
        encoding="latin1"
    )

except Exception as e:

    st.error(
        f"No se pudo cargar {TOPICS_FILE}"
    )

    st.exception(e)
    st.stop()


if "topic" not in df.columns:

    st.error(
        f"No se encontró la columna 'topic'. "
        f"Columnas encontradas: {list(df.columns)}"
    )

    st.stop()


topics = (
    df["topic"]
    .dropna()
    .astype(str)
    .tolist()
)

topics_test = topics[:N_TOPICS_TEST]

st.success(
    f"{TOPICS_FILE} cargado correctamente: "
    f"{len(topics)} topics."
)

st.write(
    f"Se procesarán los primeros {len(topics_test)} topics."
)


###############################################################################
# DATOS DE LOGIN
###############################################################################

email = st.text_input(
    "Email de DynaMed"
)

password = st.text_input(
    "Contraseña de DynaMed",
    type="password"
)


###############################################################################
# FUNCIONES AUXILIARES — RESPONDEITOR
###############################################################################

def click_js(driver, elem):

    driver.execute_script(
        "arguments[0].scrollIntoView({block:'center'});",
        elem
    )

    driver.execute_script(
        "arguments[0].click();",
        elem
    )


def click_action(driver, elem):
    """
    Click vía ActionChains.
    Si el elemento queda stale justo después del click
    porque React ya reaccionó, se considera éxito.
    """

    try:

        driver.execute_script(
            "arguments[0].scrollIntoView({block:'center'});",
            elem
        )

        time.sleep(0.3)

        ActionChains(driver).move_to_element(elem).click().perform()

        return True

    except StaleElementReferenceException:

        return True

    except Exception:

        return False


def select_other_and_not_found(driver, max_idle_passes=3):

    other_selected = 0
    not_found_selected = 0

    processed = set()

    scroll_step = 150
    current_y = 0
    idle_passes = 0

    while True:

        found_new_this_pass = False

        labels = driver.find_elements(
            By.TAG_NAME,
            "label"
        )

        for label in labels:

            try:

                text = label.text.strip()

                if text not in (
                    OTHER_TEXT,
                    NOT_FOUND_TEXT
                ):
                    continue

                unique_key = label.get_attribute("for")

                if not unique_key:
                    unique_key = (
                        text
                        + "_"
                        + str(round(label.location["y"]))
                    )

                if unique_key in processed:
                    continue

                processed.add(unique_key)

                click_js(driver, label)

                time.sleep(0.05)

                found_new_this_pass = True

                if text == OTHER_TEXT:
                    other_selected += 1
                else:
                    not_found_selected += 1

            except Exception:
                pass

        max_height = driver.execute_script(
            "return document.body.scrollHeight"
        )

        at_bottom = current_y >= max_height

        current_y += scroll_step

        driver.execute_script(
            f"window.scrollTo(0,{current_y});"
        )

        time.sleep(0.25)

        if at_bottom:

            if found_new_this_pass:
                idle_passes = 0
            else:
                idle_passes += 1

            if idle_passes >= max_idle_passes:
                break

    return other_selected, not_found_selected


def click_advance_button(driver):
    """
    Busca y pulsa el botón Continue/Submit del cuestionario.
    """

    candidates = driver.find_elements(
        By.XPATH,
        "//button[contains(@aria-label, 'Continue') "
        "or contains(@aria-label, 'Submit') "
        "or normalize-space()='Continue' "
        "or normalize-space()='Submit']"
    )

    visible_candidates = [
        e
        for e in candidates
        if e.is_displayed() and e.is_enabled()
    ]

    if not visible_candidates:
        return False

    return click_action(
        driver,
        visible_candidates[0]
    )


def click_prepare_button(driver):
    """
    Busca y pulsa el botón Prepare de un crédito disponible.
    """

    candidates = driver.find_elements(
        By.XPATH,
        "//*[normalize-space()='Prepare']"
    )

    visible_candidates = [
        e
        for e in candidates
        if e.is_displayed() and e.is_enabled()
    ]

    if not visible_candidates:
        return False

    return click_action(
        driver,
        visible_candidates[0]
    )


def select_all_credits(driver):

    all_candidates = driver.find_elements(
        By.XPATH,
        "//*[normalize-space()='All']"
    )

    for elem in all_candidates:

        try:

            click_js(driver, elem)
            return True

        except Exception:
            pass

    return False


def process_one_questionnaire(driver, status):

    total_other = 0
    total_not_found = 0

    for part in range(1, MAX_PARTS + 1):

        status.write(
            f"  · Procesando parte {part}..."
        )

        o, nf = select_other_and_not_found(
            driver
        )

        total_other += o
        total_not_found += nf

        time.sleep(0.5)

        advanced = click_advance_button(
            driver
        )

        if not advanced:

            status.write(
                "  · No hay botón de avance, "
                "cuestionario terminado."
            )

            break

        time.sleep(3)

        if "questionnaire" not in driver.current_url.lower():

            status.write(
                "  · ✓ Cuestionario completado."
            )

            break

    return total_other, total_not_found


###############################################################################
# LOGIN — SE HACE UNA SOLA VEZ
###############################################################################

def login_dynamed(driver, email, password):

    st.info("Abriendo DynaMed...")

    driver.get(LOGIN_URL)

    time.sleep(5)


    # -----------------------------------------------------------------------
    # SIGN IN
    # -----------------------------------------------------------------------

    links = driver.find_elements(
        By.TAG_NAME,
        "a"
    )

    for link in links:

        try:

            if "Sign In" in link.text.strip():

                click_js(
                    driver,
                    link
                )

                break

        except Exception:
            pass


    time.sleep(5)


    # -----------------------------------------------------------------------
    # COOKIES
    # -----------------------------------------------------------------------

    buttons = driver.find_elements(
        By.TAG_NAME,
        "button"
    )

    for button in buttons:

        try:

            if button.text.strip() == "Accept":

                click_js(
                    driver,
                    button
                )

                time.sleep(2)

                break

        except Exception:
            pass


    # -----------------------------------------------------------------------
    # EMAIL
    # -----------------------------------------------------------------------

    try:

        username = driver.find_element(
            By.ID,
            "username"
        )

        username.clear()
        username.send_keys(email)

    except Exception as e:

        st.error(
            "No se encontró el campo de email."
        )

        st.exception(e)

        return False


    # -----------------------------------------------------------------------
    # CONTINUE EMAIL
    # -----------------------------------------------------------------------

    buttons = driver.find_elements(
        By.TAG_NAME,
        "button"
    )

    for button in buttons:

        try:

            if button.text.strip() == "Continue":

                click_js(
                    driver,
                    button
                )

                break

        except Exception:
            pass


    time.sleep(5)


    # -----------------------------------------------------------------------
    # PASSWORD
    # -----------------------------------------------------------------------

    try:

        password_field = driver.find_element(
            By.ID,
            "password"
        )

        password_field.clear()
        password_field.send_keys(password)

    except Exception as e:

        st.error(
            "No se encontró el campo de contraseña."
        )

        st.exception(e)

        return False


    # -----------------------------------------------------------------------
    # LOGIN
    # -----------------------------------------------------------------------

    buttons = driver.find_elements(
        By.TAG_NAME,
        "button"
    )

    login_button = None

    for button in buttons:

        try:

            if button.text.strip() == "Continue":

                login_button = button
                break

        except Exception:
            pass


    if login_button is None:

        st.error(
            "No se encontró el botón Continue de login."
        )

        return False


    click_js(
        driver,
        login_button
    )

    time.sleep(8)

    st.success(
        "Login realizado correctamente."
    )

    return True


###############################################################################
# FASE 1 — PREGUNTEITOR
###############################################################################

def run_pregunteitor(driver, topics_test):

    st.write("---")
    st.header("📚 FASE 1/2 — Pregunteitor")

    progress = st.progress(0)

    processed_topics = 0

    for number, topic in enumerate(
        topics_test,
        start=1
    ):

        st.write("---")

        st.write(
            f"**Topic {number}/{len(topics_test)}: {topic}**"
        )


        # -------------------------------------------------------------------
        # VOLVER A LA PÁGINA PRINCIPAL
        # -------------------------------------------------------------------

        driver.get(
            "https://www.dynamed.com"
        )

        time.sleep(5)


        # -------------------------------------------------------------------
        # ESPERAR AL BUSCADOR
        # -------------------------------------------------------------------

        search_box = None

        for _ in range(20):

            try:

                search_box = driver.find_element(
                    By.ID,
                    "autosuggest"
                )

                break

            except Exception:

                time.sleep(1)


        if search_box is None:

            st.warning(
                "⚠ No se encontró el buscador de DynaMed."
            )

            continue


        # -------------------------------------------------------------------
        # LIMPIAR BUSCADOR
        # -------------------------------------------------------------------

        search_box.click()

        search_box.send_keys(
            Keys.CONTROL,
            "a"
        )

        search_box.send_keys(
            Keys.BACKSPACE
        )

        time.sleep(1)


        # -------------------------------------------------------------------
        # ESCRIBIR TOPIC
        # -------------------------------------------------------------------

        search_box.send_keys(
            topic
        )

        time.sleep(2)


        # -------------------------------------------------------------------
        # BUSCAR
        # -------------------------------------------------------------------

        search_box.send_keys(
            Keys.ENTER
        )

        time.sleep(6)


        # -------------------------------------------------------------------
        # BUSCAR RESULTADO DE CONTENIDO
        # -------------------------------------------------------------------

        links = driver.find_elements(
            By.TAG_NAME,
            "a"
        )

        target_link = None

        for link in links:

            try:

                text = link.text.strip()

                href = link.get_attribute(
                    "href"
                )

                if not href:
                    continue


                is_content = (
                    "/condition/" in href
                    or "/drug-monograph/" in href
                    or "/management/" in href
                    or "/evaluation/" in href
                    or "/prevention/" in href
                    or "/procedure/" in href
                    or "/approach-to/" in href
                )

                if is_content:

                    target_link = link
                    break

            except Exception:
                pass


        # -------------------------------------------------------------------
        # NO ENCONTRADO
        # -------------------------------------------------------------------

        if target_link is None:

            st.warning(
                "⚠ No se encontró un resultado de contenido."
            )

            continue


        # -------------------------------------------------------------------
        # RESULTADO ENCONTRADO
        # -------------------------------------------------------------------

        target_text = target_link.text.strip()

        st.write(
            f"✓ encontrado → {target_text}"
        )


        # -------------------------------------------------------------------
        # ABRIR RESULTADO
        # -------------------------------------------------------------------

        driver.execute_script(
            "arguments[0].click();",
            target_link
        )

        time.sleep(6)


        # -------------------------------------------------------------------
        # COMPROBAR APERTURA
        # -------------------------------------------------------------------

        current_url = driver.current_url

        if (
            "/condition/" in current_url
            or "/drug-monograph/" in current_url
            or "/management/" in current_url
            or "/evaluation/" in current_url
            or "/prevention/" in current_url
            or "/procedure/" in current_url
            or "/approach-to/" in current_url
        ):

            st.write(
                "✓ abierto"
            )

        else:

            st.warning(
                "⚠ El resultado no parece haberse "
                "abierto correctamente."
            )

        processed_topics += 1

        progress.progress(
            number / len(topics_test)
        )


    st.success(
        f"✓ Pregunteitor terminado: "
        f"{processed_topics}/{len(topics_test)} topics procesados."
    )

    return processed_topics


###############################################################################
# FASE 2 — RESPONDEITOR
###############################################################################

def run_respondeitor(driver):

    st.write("---")
    st.header("🎓 FASE 2/2 — Respondeitor")

    st.info(
        "El login ya está realizado. "
        "Se reutiliza la misma sesión de DynaMed."
    )


    # -----------------------------------------------------------------------
    # AVAILABLE CREDITS
    # -----------------------------------------------------------------------

    st.info(
        "Abriendo Available Credits..."
    )

    driver.get(
        AVAILABLE_CREDITS_URL
    )

    try:

        WebDriverWait(
            driver,
            PAGE_TIMEOUT
        ).until(
            EC.presence_of_element_located(
                (
                    By.CSS_SELECTOR,
                    "[data-element='tabPanels']"
                )
            )
        )

    except Exception as e:

        st.error(
            "No se pudo cargar la página de Available Credits."
        )

        st.exception(e)

        return 0, 0, 0


    time.sleep(2)

    select_all_credits(
        driver
    )

    st.success(
        "Opción 'All' seleccionada."
    )


    # -----------------------------------------------------------------------
    # PROCESAR TODOS LOS CRÉDITOS
    # -----------------------------------------------------------------------

    total_credits_done = 0
    grand_total_other = 0
    grand_total_not_found = 0


    for credit_number in range(
        1,
        MAX_CREDITS + 1
    ):

        st.write("---")

        st.write(
            f"**Crédito {credit_number}**"
        )

        status = st.empty()


        # -------------------------------------------------------------------
        # PREPARE
        # -------------------------------------------------------------------

        prepared = click_prepare_button(
            driver
        )

        if not prepared:

            st.write(
                "No quedan más créditos disponibles. Fin."
            )

            break


        status.write(
            "· Botón Prepare pulsado, "
            "esperando cuestionario..."
        )


        # -------------------------------------------------------------------
        # ESPERAR CUESTIONARIO
        # -------------------------------------------------------------------

        try:

            WebDriverWait(
                driver,
                20
            ).until(
                lambda d:
                "questionnaire"
                in d.current_url.lower()
            )

        except Exception:

            status.write(
                "⚠ No se detectó el cuestionario "
                "tras pulsar Prepare. "
                "Se pasa al siguiente crédito."
            )

            driver.get(
                AVAILABLE_CREDITS_URL
            )

            time.sleep(3)

            select_all_credits(
                driver
            )

            continue


        # -------------------------------------------------------------------
        # PROCESAR CUESTIONARIO
        # -------------------------------------------------------------------

        o, nf = process_one_questionnaire(
            driver,
            status
        )

        grand_total_other += o
        grand_total_not_found += nf

        total_credits_done += 1

        st.write(
            f"✓ Crédito completado. "
            f"Other: {o} · "
            f"I did not find...: {nf}"
        )


        # -------------------------------------------------------------------
        # VOLVER A AVAILABLE CREDITS
        # -------------------------------------------------------------------

        driver.get(
            AVAILABLE_CREDITS_URL
        )

        try:

            WebDriverWait(
                driver,
                PAGE_TIMEOUT
            ).until(
                EC.presence_of_element_located(
                    (
                        By.CSS_SELECTOR,
                        "[data-element='tabPanels']"
                    )
                )
            )

        except Exception:
            pass


        time.sleep(2)

        select_all_credits(
            driver
        )


    # -----------------------------------------------------------------------
    # RESUMEN
    # -----------------------------------------------------------------------

    st.write("---")

    st.success(
        f"🎉 Respondeitor terminado. "
        f"Créditos completados: "
        f"{total_credits_done}"
    )

    st.write(
        f"Total 'Other' seleccionados: "
        f"{grand_total_other}  \n"
        f"Total 'I did not find...': "
        f"{grand_total_not_found}"
    )

    return (
        total_credits_done,
        grand_total_other,
        grand_total_not_found
    )


###############################################################################
# BOTÓN PRINCIPAL — TODO EL PROCESO
###############################################################################

if st.button(
    "🚀 Ejecutar Pregunteitor + Respondeitor"
):

    if not email or not password:

        st.warning(
            "Introduce email y contraseña."
        )

        st.stop()


    # =======================================================================
    # CHROME
    # =======================================================================

    options = Options()

    options.add_argument(
        "--headless"
    )

    options.add_argument(
        "--no-sandbox"
    )

    options.add_argument(
        "--disable-dev-shm-usage"
    )

    options.add_argument(
        "--window-size=1920,1080"
    )

    # Configuración utilizada por el Respondeitor
    # para Streamlit Cloud.
    options.binary_location = "/usr/bin/chromium"


    driver = webdriver.Chrome(
        options=options,
        service=webdriver.chrome.service.Service(
            "/usr/bin/chromedriver"
        )
    )


    try:

        # ================================================================
        # LOGIN — UNA SOLA VEZ
        # ================================================================

        login_ok = login_dynamed(
            driver,
            email,
            password
        )

        if not login_ok:

            driver.quit()
            st.stop()


        # ================================================================
        # FASE 1 — PREGUNTEITOR
        # ================================================================

        run_pregunteitor(
            driver,
            topics_test
        )


        # ================================================================
        # FASE 2 — RESPONDEITOR
        # ================================================================

        run_respondeitor(
            driver
        )


        # ================================================================
        # FIN
        # ================================================================

        st.write("---")

        st.success(
            "🎉🎉 PROCESO COMPLETO TERMINADO 🎉🎉"
        )

    except Exception as e:

        st.error(
            "Se produjo un error durante el proceso."
        )

        st.exception(e)

    finally:

        driver.quit()
