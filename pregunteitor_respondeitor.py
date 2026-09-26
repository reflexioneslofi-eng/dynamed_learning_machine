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


st.set_page_config(
    page_title="Pregunteitor + Respondeitor",
    page_icon="🎓"
)

st.title("🎓 Pregunteitor + Respondeitor")

st.write(
    "1️⃣ Busca los topics en DynaMed para generar créditos CME.  \n"
    "2️⃣ Reclama automáticamente todos los créditos generados."
)


# =========================================================
# CONFIGURACIÓN GENERAL
# =========================================================

LOGIN_URL = "https://www.dynamed.com"

AVAILABLE_CREDITS_URL = "https://www.dynamed.com/cme/available-credits"

PAGE_TIMEOUT = 60

N_TOPICS_TEST = 99

CSV_OPTIONS = [f"topics_{i}.csv" for i in range(1, 11)]

OTHER_TEXT = "Other"

NOT_FOUND_TEXT = (
    "I did not find that the information answered my clinical question"
)

MAX_PARTS = 10
MAX_CREDITS = 200


# =========================================================
# SELECCIÓN DE CSV
# =========================================================

TOPICS_FILE = st.selectbox(
    "Selecciona el archivo de topics a usar",
    CSV_OPTIONS
)

try:

    df = pd.read_csv(
        TOPICS_FILE,
        sep=";",
        encoding="latin1"
    )

except Exception as e:

    st.error(f"No se pudo cargar {TOPICS_FILE}")

    st.exception(e)

    st.stop()

if "topic" not in df.columns:

    st.error(
        f"No se encontró la columna 'topic'. "
        f"Columnas encontradas: {list(df.columns)}"
    )

    st.stop()

topics = df["topic"].dropna().astype(str).tolist()

topics_test = topics[:N_TOPICS_TEST]

st.success(f"{TOPICS_FILE} cargado correctamente: {len(topics)} topics.")

st.write(f"Se probarán los primeros {len(topics_test)} topics.")


# =========================================================
# DATOS DE LOGIN
# =========================================================

email = st.text_input("Email de DynaMed")

password = st.text_input("Contraseña de DynaMed", type="password")


# =========================================================
# FUNCIONES AUXILIARES COMUNES
# =========================================================

def click_js(driver, elem):

    driver.execute_script(
        "arguments[0].scrollIntoView({block:'center'});",
        elem
    )

    driver.execute_script("arguments[0].click();", elem)


def click_action(driver, elem):
    """Click 'real' vía ActionChains. Si el elemento queda stale
    justo después (porque React ya reaccionó al click), lo
    consideramos un éxito."""

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


def wait_for_element(driver, by, value, timeout=25):
    """Espera explícita a que un elemento exista en el DOM."""

    return WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((by, value))
    )


def click_button_with_text(driver, text, timeout=25):
    """Espera a que aparezca un <button> cuyo texto sea exactamente
    'text', y lo pulsa. Lanza excepción si no aparece a tiempo."""

    def find_button(d):

        buttons = d.find_elements(By.TAG_NAME, "button")

        for button in buttons:

            try:

                if button.text.strip() == text:
                    return button

            except Exception:
                pass

        return False

    button = WebDriverWait(driver, timeout).until(find_button)

    click_js(driver, button)

    return button


def login_dynamed(driver, email, password):

    driver.get(LOGIN_URL)

    # Esperar a que la home cargue de verdad antes de buscar "Sign In"
    wait_for_element(driver, By.TAG_NAME, "a", timeout=30)

    # SIGN IN
    def find_sign_in(d):

        links = d.find_elements(By.TAG_NAME, "a")

        for link in links:

            try:

                if "Sign In" in link.text.strip():
                    return link

            except Exception:
                pass

        return False

    sign_in_link = WebDriverWait(driver, 30).until(find_sign_in)

    click_js(driver, sign_in_link)

    # COOKIES (opcional: si no aparece en unos segundos, seguimos)
    try:

        def find_accept(d):

            buttons = d.find_elements(By.TAG_NAME, "button")

            for button in buttons:

                try:

                    if button.text.strip() == "Accept":
                        return button

                except Exception:
                    pass

            return False

        accept_button = WebDriverWait(driver, 8).until(find_accept)

        click_js(driver, accept_button)

    except Exception:
        pass

    # EMAIL: esperar explícitamente a que exista el campo
    try:

        username = wait_for_element(driver, By.ID, "username", timeout=30)

    except Exception as e:

        driver.save_screenshot("/tmp/debug_login_email.png")

        raise Exception(
            "No apareció el campo de email a tiempo. "
            "Captura guardada en /tmp/debug_login_email.png"
        ) from e

    username.clear()

    username.send_keys(email)

    # CONTINUE tras el email
    try:

        click_button_with_text(driver, "Continue", timeout=15)

    except Exception as e:

        driver.save_screenshot("/tmp/debug_login_continue1.png")

        raise Exception(
            "No apareció el botón Continue tras el email. "
            "Captura guardada en /tmp/debug_login_continue1.png"
        ) from e

    # PASSWORD: esperar explícitamente a que exista el campo
    try:

        password_field = wait_for_element(driver, By.ID, "password", timeout=30)

    except Exception as e:

        driver.save_screenshot("/tmp/debug_login_password.png")

        raise Exception(
            "No apareció el campo de contraseña a tiempo. "
            "Captura guardada en /tmp/debug_login_password.png"
        ) from e

    password_field.clear()

    password_field.send_keys(password)

    # LOGIN: pulsar el Continue final
    try:

        click_button_with_text(driver, "Continue", timeout=15)

    except Exception as e:

        driver.save_screenshot("/tmp/debug_login_continue2.png")

        raise Exception(
            "No apareció el botón Continue final de login. "
            "Captura guardada en /tmp/debug_login_continue2.png"
        ) from e

    # Esperar a que el login se complete de verdad (desaparece el
    # formulario y cargamos ya la web logueados)
    try:

        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )

        time.sleep(3)  # pequeño margen para que la SPA termine de renderizar

    except Exception:
        pass


# =========================================================
# FUNCIONES DE PREGUNTEITOR (búsqueda de topics)
# =========================================================

def search_all_topics(driver, topics_test, status_container):

    for number, topic in enumerate(topics_test, start=1):

        status_container.write(
            f"**Topic {number}/{len(topics_test)}: {topic}**"
        )

        driver.get("https://www.dynamed.com")

        time.sleep(5)

        search_box = None

        for _ in range(20):

            try:

                search_box = driver.find_element(By.ID, "autosuggest")

                break

            except Exception:

                time.sleep(1)

        if search_box is None:

            status_container.write("⚠ no se encontró el buscador de DynaMed")

            continue

        search_box.click()

        search_box.send_keys(Keys.CONTROL, "a")

        search_box.send_keys(Keys.BACKSPACE)

        time.sleep(1)

        search_box.send_keys(topic)

        time.sleep(2)

        search_box.send_keys(Keys.ENTER)

        time.sleep(6)

        links = driver.find_elements(By.TAG_NAME, "a")

        target_link = None

        for link in links:

            try:

                href = link.get_attribute("href")

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

        if target_link is None:

            status_container.write("⚠ no se encontró un resultado de contenido")

            continue

        target_text = target_link.text.strip()

        status_container.write(f"✓ encontrado → {target_text}")

        driver.execute_script("arguments[0].click();", target_link)

        time.sleep(6)

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

            status_container.write("✓ abierto")

        else:

            status_container.write(
                "⚠ el resultado no parece haberse abierto correctamente"
            )


# =========================================================
# FUNCIONES DE RESPONDEITOR (reclamar créditos)
# =========================================================

def select_other_and_not_found(driver, max_idle_passes=3):

    other_selected = 0
    not_found_selected = 0

    processed = set()

    scroll_step = 150

    current_y = 0

    idle_passes = 0

    while True:

        found_new_this_pass = False

        labels = driver.find_elements(By.TAG_NAME, "label")

        for label in labels:

            try:

                text = label.text.strip()

                if text not in (OTHER_TEXT, NOT_FOUND_TEXT):
                    continue

                unique_key = label.get_attribute("for")

                if not unique_key:
                    unique_key = (
                        text + "_" + str(round(label.location["y"]))
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

        driver.execute_script(f"window.scrollTo(0,{current_y});")

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

    candidates = driver.find_elements(
        By.XPATH,
        "//button[contains(@aria-label, 'Continue') "
        "or contains(@aria-label, 'Submit') "
        "or normalize-space()='Continue' "
        "or normalize-space()='Submit']"
    )

    visible_candidates = [
        e for e in candidates
        if e.is_displayed() and e.is_enabled()
    ]

    if not visible_candidates:
        return False

    return click_action(driver, visible_candidates[0])


def click_prepare_button(driver):

    candidates = driver.find_elements(
        By.XPATH,
        "//*[normalize-space()='Prepare']"
    )

    visible_candidates = [
        e for e in candidates
        if e.is_displayed() and e.is_enabled()
    ]

    if not visible_candidates:
        return False

    return click_action(driver, visible_candidates[0])


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

        status.write(f"  · Procesando parte {part}...")

        o, nf = select_other_and_not_found(driver)

        total_other += o
        total_not_found += nf

        time.sleep(0.5)

        advanced = click_advance_button(driver)

        if not advanced:
            status.write("  · No hay botón de avance, cuestionario terminado.")
            break

        time.sleep(3)

        if "questionnaire" not in driver.current_url.lower():
            status.write("  · ✓ Cuestionario completado.")
            break

    return total_other, total_not_found


def claim_all_credits(driver):

    total_credits_done = 0
    grand_total_other = 0
    grand_total_not_found = 0

    driver.get(AVAILABLE_CREDITS_URL)

    try:

        WebDriverWait(driver, PAGE_TIMEOUT).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "[data-element='tabPanels']")
            )
        )

    except Exception as e:

        st.error("No se pudo cargar la página de Available Credits.")

        st.exception(e)

        return total_credits_done, grand_total_other, grand_total_not_found

    time.sleep(2)

    select_all_credits(driver)

    st.success("Opción 'All' seleccionada.")

    for credit_number in range(1, MAX_CREDITS + 1):

        st.write("---")

        st.write(f"**Crédito {credit_number}**")

        status = st.empty()

        prepared = click_prepare_button(driver)

        if not prepared:

            st.write("No quedan más créditos disponibles. Fin.")

            break

        status.write("· Botón Prepare pulsado, esperando cuestionario...")

        try:

            WebDriverWait(driver, 20).until(
                lambda d: "questionnaire" in d.current_url.lower()
            )

        except Exception:

            status.write(
                "⚠ No se detectó el cuestionario tras pulsar Prepare. "
                "Se pasa al siguiente crédito."
            )

            driver.get(AVAILABLE_CREDITS_URL)

            time.sleep(3)

            select_all_credits(driver)

            continue

        o, nf = process_one_questionnaire(driver, status)

        grand_total_other += o
        grand_total_not_found += nf

        total_credits_done += 1

        st.write(
            f"✓ Crédito completado. Other: {o} · "
            f"I did not find...: {nf}"
        )

        driver.get(AVAILABLE_CREDITS_URL)

        try:

            WebDriverWait(driver, PAGE_TIMEOUT).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "[data-element='tabPanels']")
                )
            )

        except Exception:
            pass

        time.sleep(2)

        select_all_credits(driver)

    return total_credits_done, grand_total_other, grand_total_not_found


# =========================================================
# BOTÓN PRINCIPAL
# =========================================================

if st.button("🚀 Ejecutar Pregunteitor + Respondeitor"):

    if not email or not password:

        st.warning("Introduce email y contraseña.")

        st.stop()

    options = Options()

    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.binary_location = "/usr/bin/chromium"

    driver = webdriver.Chrome(
        options=options,
        service=webdriver.chrome.service.Service("/usr/bin/chromedriver")
    )

    # ---------------------------------------------------
    # LOGIN (una sola vez para todo el proceso)
    # ---------------------------------------------------

    st.info("Abriendo DynaMed e iniciando sesión...")

    try:

        login_dynamed(driver, email, password)

    except Exception as e:

        st.error("No se pudo completar el login.")

        st.exception(e)

        # Si login_dynamed guardó una captura de diagnóstico, mostrarla
        import glob

        screenshots = glob.glob("/tmp/debug_login_*.png")

        for shot in screenshots:

            st.image(shot, caption=shot)

        driver.quit()

        st.stop()

    st.success("Login realizado correctamente.")

    # ---------------------------------------------------
    # FASE 1: PREGUNTEITOR
    # ---------------------------------------------------

    st.header("1️⃣ Pregunteitor: buscando topics")

    topics_status = st.container()

    search_all_topics(driver, topics_test, topics_status)

    st.success(f"🎉 Búsqueda de topics terminada: {len(topics_test)} topics.")

    # ---------------------------------------------------
    # FASE 2: RESPONDEITOR
    # ---------------------------------------------------

    st.header("2️⃣ Respondeitor: reclamando créditos")

    total_credits_done, grand_total_other, grand_total_not_found = (
        claim_all_credits(driver)
    )

    st.write("---")

    st.success(
        f"🎉 Proceso terminado. Créditos completados: "
        f"{total_credits_done}"
    )

    st.write(
        f"Total 'Other' seleccionados: {grand_total_other}  \n"
        f"Total 'I did not find...' seleccionados: {grand_total_not_found}"
    )

    driver.quit()
