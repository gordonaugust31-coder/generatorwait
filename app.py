"""
🌐 CleanMeta — Website Generator
Покроковий чат-візард для генерації унікальних PHP/HTML сайтів.
"""

import streamlit as st
import zipfile
import os
import io
import json
import re
import time
import random
import string
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# ─── Page Config ───
st.set_page_config(
    page_title="CleanMeta — Генератор сайтів",
    page_icon="🌐",
    layout="centered",
)

# ─── CSS ───
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&display=swap');
.stApp { background: #0e1117; }
div[data-testid="stChatMessage"] { font-size: 0.95rem; }
div[data-testid="stChatMessage"] p { margin-bottom: 0.4rem; }
</style>
""", unsafe_allow_html=True)

TEMPLATE_ZIP_PATH = Path(__file__).parent / "template.zip"

# ─── Template constants ───
TPL_DOMAIN = "mindfulroutineflow.info"
TPL_BRAND = "Mindful Routine Flow"
TPL_GEO = "Groningen"
TPL_ADDRESS = "Herestraat 67, 9711 LC Groningen, Netherlands"
TPL_PHONE = "+31 50 739 2184"
TPL_EMAIL = "office@mindfulroutineflow.info"
TPL_LANG = "nl"

LANG_CODES = {
    "English": "en", "Deutsch": "de", "Français": "fr", "Español": "es",
    "Italiano": "it", "Português": "pt", "Nederlands": "nl", "Polski": "pl",
    "Čeština": "cs", "Slovenčina": "sk", "Română": "ro", "Magyar": "hu",
    "Українська": "uk", "Русский": "ru", "日本語": "ja", "中文": "zh",
    "한국어": "ko", "العربية": "ar", "Türkçe": "tr", "Svenska": "sv",
    "Norsk": "no", "Dansk": "da", "Suomi": "fi", "Ελληνικά": "el",
    "Bahasa Indonesia": "id", "Tiếng Việt": "vi", "ภาษาไทย": "th",
    "हिन्दी": "hi", "বাংলা": "bn", "Filipino": "fil",
}


# ═══════════════════════════════════════
# Session state
# ═══════════════════════════════════════
def init_state():
    defaults = {
        "step": 0,
        "messages": [],
        "format": None,
        "num_sites": 1,
        "geo": "",
        "language": "",
        "has_domains": None,
        "domains": [],
        "contacts_raw": "",
        "contacts": {},
        "theme_mode": None,
        "theme_niche": "",
        "themes": [],
        "has_seo": None,
        "seo_keywords": "",
        "has_stopwords": None,
        "stop_words": "",
        "has_extra": None,
        "extra_requirements": "",
        "generating": False,
        "gen_result": None,
        "api_key": "",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_state()


def add_msg(role, content):
    st.session_state.messages.append({"role": role, "content": content})

def bot(text):
    add_msg("assistant", text)

def usr(text):
    add_msg("user", text)

def reset_all():
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    init_state()


# ═══════════════════════════════════════
# Helpers
# ═══════════════════════════════════════
def validate_domain(d):
    d = d.strip().lower().replace("https://","").replace("http://","").replace("www.","").rstrip("/")
    if re.match(r'^[a-z0-9]([a-z0-9\-]*[a-z0-9])?(\.[a-z]{2,})+$', d):
        return d
    return None

def parse_domains(text):
    raw = re.split(r'[\n,;\s]+', text)
    out = []
    for d in raw:
        v = validate_domain(d)
        if v and v not in out:
            out.append(v)
    return out

def parse_contacts(text, domains):
    contacts = {}
    lines = text.strip().split("\n")
    for line in lines:
        line = line.strip()
        if not line:
            continue
        m = re.match(r'^([a-z0-9\-]+\.[a-z]{2,}[^\s]*)\s*[:;]\s*(.*)', line, re.I)
        if m:
            dom = validate_domain(m.group(1))
            if dom:
                contacts[dom] = _extract_contact(m.group(2))
    if not contacts:
        parts = _extract_contact(" ".join(lines))
        for dom in domains:
            contacts[dom] = parts.copy()
    if contacts:
        default = list(contacts.values())[0]
        for dom in domains:
            if dom not in contacts:
                contacts[dom] = default.copy()
    return contacts

def _extract_contact(text):
    phone, email, address = "", "", text
    em = re.search(r'[\w\.\-+]+@[\w\.\-]+\.\w+', text)
    if em:
        email = em.group(0)
        address = address.replace(email, "")
    ph = re.search(r'[\+]?[\d\s\-\(\)]{7,20}', text)
    if ph:
        phone = ph.group(0).strip()
        address = address.replace(phone, "")
    address = re.sub(r'^[,;:\s]+|[,;:\s]+$', '', address).strip()
    return {"address": address, "phone": phone, "email": email}

def brand_from_domain(domain):
    name = domain.split(".")[0]
    name = re.sub(r'([a-z])([A-Z])', r'\1 \2', name)
    name = name.replace("-"," ").replace("_"," ")
    return name.title()


# ═══════════════════════════════════════
# Claude API
# ═══════════════════════════════════════
def call_claude(api_key, system, prompt, max_tokens=8000):
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    for attempt in range(3):
        try:
            msg = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=max_tokens,
                system=system,
                messages=[{"role":"user","content":prompt}],
            )
            return msg.content[0].text
        except Exception as e:
            err = str(e).lower()
            if ("rate" in err or "overloaded" in err or "529" in str(e) or "529" in err) and attempt < 2:
                time.sleep(20 * (attempt + 1))
            else:
                raise

def _clean_json(text):
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r'^```\w*\n?', '', text)
        text = re.sub(r'\n?```$', '', text)
    return text

def generate_themes(api_key, niche, count, language):
    r = call_claude(api_key,
        "Generate website themes. Respond ONLY with JSON array, no markdown.",
        f"Generate exactly {count} DIFFERENT specific website themes within '{niche}'. "
        f"Language: {language}. Return JSON array of {count} strings.",
        max_tokens=2000)
    return json.loads(_clean_json(r))

def generate_nav(api_key, niche, language, stop_words):
    r = call_claude(api_key,
        f"Create nav labels. ONLY valid JSON. Never use: {stop_words}",
        f"Create navigation labels in {language} for a '{niche}' website.\n"
        f"Pages: home, main listing, secondary feature, about us, contact.\n"
        f'Return: {{"home":"...","listing_page":"...","listing_slug":"slug",'
        f'"feature_page":"...","feature_slug":"slug",'
        f'"about":"...","about_slug":"slug",'
        f'"contact":"...","contact_cta":"..."}}\n'
        f"Slugs: lowercase ASCII hyphens only.",
        max_tokens=500)
    return json.loads(_clean_json(r))

def generate_page(api_key, template_html, page_type, cfg, nav, stop_words, seo_kw, extra):
    ext = ".php" if cfg["format"]=="php" else ".html"
    fmap = {
        "listing": f"{nav.get('listing_slug','services')}{ext}",
        "feature": f"{nav.get('feature_slug','features')}{ext}",
        "about": f"{nav.get('about_slug','about')}{ext}",
    }
    lc = LANG_CODES.get(cfg["language"], "en")

    system = (
        f"Expert web developer. Rewrite HTML page content.\n"
        f"PRESERVE exact HTML structure, CSS, Tailwind, data-attrs, JS refs.\n"
        f"REPLACE ALL text with NEW unique content in {cfg['language']}.\n"
        f"Niche: {cfg['theme']} | Brand: {cfg['brand']} | Geo: {cfg['geo']}\n"
        f"Domain: {cfg['domain']} | Address: {cfg['address']}\n"
        f"Phone: {cfg['phone']} | Email: {cfg['email']}\n"
        f"NEVER use: {stop_words}\n"
        f"Keep image src paths, update alt in {cfg['language']}.\n"
        f"Update ALL JSON-LD, meta tags, OG tags.\n"
        f"Nav: Home→index{ext}, {nav.get('listing_page','')}→{fmap['listing']}, "
        f"{nav.get('feature_page','')}→{fmap['feature']}, "
        f"{nav.get('about','')}→{fmap['about']}, Contact→contact{ext}\n"
        f"Legal: privacy-policy{ext}, cookie-policy{ext}, terms-of-service{ext}\n"
        f"SEO keywords: {seo_kw}\n"
        f"Extra: {extra}\n"
        f"html lang=\"{lc}\"\n"
        f"Output ONLY complete HTML, no markdown/fences."
    )
    result = call_claude(api_key, system, f"Rewrite this {page_type} page:\n\n{template_html}", max_tokens=16000)
    result = result.strip()
    if result.startswith("```"):
        result = re.sub(r'^```\w*\n?', '', result)
        result = re.sub(r'\n?```$', '', result)
    idx = result.find("<!DOCTYPE")
    if idx < 0: idx = result.find("<html")
    if idx > 0: result = result[idx:]
    return result

def do_replace(html, cfg, nav, fmt):
    ext = ".php" if fmt == "php" else ".html"
    fmap = {
        "listing": f"{nav.get('listing_slug','services')}{ext}",
        "feature": f"{nav.get('feature_slug','features')}{ext}",
        "about": f"{nav.get('about_slug','about')}{ext}",
    }
    lc = LANG_CODES.get(cfg["language"], "en")
    reps = [
        (TPL_DOMAIN, cfg["domain"]), (TPL_BRAND, cfg["brand"]),
        (TPL_GEO, cfg["geo"]), (TPL_ADDRESS, cfg["address"]),
        (TPL_PHONE, cfg["phone"]), (TPL_EMAIL, cfg["email"]),
        (f'lang="{TPL_LANG}"', f'lang="{lc}"'),
        ('href="recepten.php"', f'href="{fmap["listing"]}"'),
        ('href="maaltijdplanning.php"', f'href="{fmap["feature"]}"'),
        ('href="over-ons.php"', f'href="{fmap["about"]}"'),
    ]
    if fmt == "html":
        for pg in ["index","contact","privacy-policy","cookie-policy","terms-of-service"]:
            reps.append((f'href="{pg}.php"', f'href="{pg}.html"'))
    for old,new in reps:
        html = html.replace(old, new)
    return html


# ═══════════════════════════════════════
# Build pipeline
# ═══════════════════════════════════════
def extract_template():
    files = {}
    with zipfile.ZipFile(str(TEMPLATE_ZIP_PATH), 'r') as zf:
        for name in zf.namelist():
            if not name.endswith('/'):
                files[name] = zf.read(name)
    return files

def gen_sitemap(domain, nav, fmt):
    ext = ".php" if fmt=="php" else ".html"
    today = datetime.now().strftime("%Y-%m-%d")
    pages = [f"index{ext}", f"{nav.get('listing_slug','services')}{ext}",
             f"{nav.get('feature_slug','features')}{ext}", f"{nav.get('about_slug','about')}{ext}",
             f"contact{ext}", f"privacy-policy{ext}", f"cookie-policy{ext}",
             f"terms-of-service{ext}", "404.html"]
    urls = "".join(f'  <url>\n    <loc>https://{domain}/{p}</loc>\n    <lastmod>{today}</lastmod>\n    <changefreq>monthly</changefreq>\n    <priority>0.8</priority>\n  </url>\n' for p in pages)
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{urls}</urlset>'

def gen_robots(domain):
    return f"User-agent: *\nAllow: /\n\nSitemap: https://{domain}/sitemap.xml\n"

def gen_htaccess(domain):
    esc = domain.replace('.','\\\\.')
    return (
        "<IfModule mod_rewrite.c>\n    RewriteEngine On\n\n"
        "    RewriteCond %{HTTPS} off\n    RewriteRule ^(.*)$ https://%{HTTP_HOST}%{REQUEST_URI} [L,R=301]\n\n"
        f"    RewriteCond %{{HTTP_HOST}} ^www\\.{esc}$ [NC]\n    RewriteRule ^(.*)$ https://{domain}/$1 [L,R=301]\n\n"
        "    RewriteCond %{REQUEST_FILENAME} !-d\n    RewriteCond %{REQUEST_FILENAME}\\.php -f\n"
        "    RewriteRule ^([^/]+)/?$ $1.php [L]\n\n"
        "    RewriteCond %{REQUEST_FILENAME} !-d\n    RewriteCond %{REQUEST_FILENAME}\\.html -f\n"
        "    RewriteRule ^([^/]+)/?$ $1.html [L]\n\n"
        "    DirectoryIndex index.php index.html\n</IfModule>\n\n"
        "ErrorDocument 404 /404.html\n\n"
        "<IfModule mod_headers.c>\n"
        '    Header set X-Content-Type-Options "nosniff"\n'
        '    Header set X-Frame-Options "SAMEORIGIN"\n'
        "</IfModule>\n\n"
        "<IfModule mod_expires.c>\n    ExpiresActive On\n"
        '    ExpiresByType image/webp "access plus 1 year"\n'
        '    ExpiresByType text/css "access plus 1 month"\n'
        '    ExpiresByType application/javascript "access plus 1 month"\n'
        "</IfModule>\n"
    )

def build_one_site(api_key, site_cfg, tpl, fmt, stop_words, seo_kw, extra, log_fn=None):
    output = {}
    ext = ".php" if fmt=="php" else ".html"

    if log_fn: log_fn(f"🧭 Навігація...")
    nav = generate_nav(api_key, site_cfg["theme"], site_cfg["language"], stop_words)
    time.sleep(2)

    fmap = {
        "recepten.php": f"{nav.get('listing_slug','services')}{ext}",
        "maaltijdplanning.php": f"{nav.get('feature_slug','features')}{ext}",
        "over-ons.php": f"{nav.get('about_slug','about')}{ext}",
    }

    ai_pages = [
        ("index.php", "Home"),
        ("recepten.php", nav.get("listing_page","Listing")),
        ("maaltijdplanning.php", nav.get("feature_page","Feature")),
        ("over-ons.php", nav.get("about","About")),
        ("contact.php", "Contact"),
        ("privacy-policy.php", "Privacy Policy"),
        ("cookie-policy.php", "Cookie Policy"),
        ("terms-of-service.php", "Terms of Service"),
    ]

    for tpl_name, page_type in ai_pages:
        if log_fn: log_fn(f"📝 {page_type}...")
        tpl_html = tpl.get(tpl_name, b"").decode("utf-8", errors="replace")
        if not tpl_html:
            continue
        try:
            new_html = generate_page(api_key, tpl_html, page_type, site_cfg, nav, stop_words, seo_kw, extra)
            out_name = fmap.get(tpl_name, tpl_name)
            if fmt == "html": out_name = out_name.replace(".php",".html")
            output[out_name] = new_html.encode("utf-8")
            if log_fn: log_fn(f"✅ {page_type}")
        except Exception as e:
            if log_fn: log_fn(f"❌ {page_type} — ПОМИЛКА: {str(e)[:200]}")
        time.sleep(3)

    # 404
    if log_fn: log_fn(f"📝 404 сторінка...")
    try:
        h404 = tpl.get("404.html", b"").decode("utf-8", errors="replace")
        new_404 = generate_page(api_key, h404, "404 Error page", site_cfg, nav, stop_words, seo_kw, extra)
        output["404.html"] = new_404.encode("utf-8")
        if log_fn: log_fn(f"✅ 404")
    except Exception as e:
        h404 = tpl.get("404.html", b"").decode("utf-8", errors="replace")
        h404 = do_replace(h404, site_cfg, nav, fmt)
        output["404.html"] = h404.encode("utf-8")
        if log_fn: log_fn(f"⚠️ 404 — fallback заміна")

    # Config files
    output["sitemap.xml"] = gen_sitemap(site_cfg["domain"], nav, fmt).encode("utf-8")
    output["robots.txt"] = gen_robots(site_cfg["domain"]).encode("utf-8")
    output[".htaccess"] = gen_htaccess(site_cfg["domain"]).encode("utf-8")

    # Static assets
    for name, data in tpl.items():
        if name.startswith(("css/","js/","images/")):
            output[name] = data
        elif name in ("favicon.ico","favicon-16x16.png","favicon-32x32.png",
                       "favicon-192x192.png","apple-touch-icon.png"):
            output[name] = data

    return output


def run_generation(api_key):
    s = st.session_state
    fmt = s.format
    stop_words = s.stop_words if s.has_stopwords else ""
    seo_kw = s.seo_keywords if s.has_seo else ""
    extra = s.extra_requirements if s.has_extra else ""

    tpl = extract_template()
    total = len(s.domains)

    progress_bar = st.progress(0.0, text="Підготовка...")
    log_area = st.container()
    logs = []

    def log(msg):
        logs.append(f"`{datetime.now().strftime('%H:%M:%S')}` {msg}")
        with log_area:
            for entry in logs[-6:]:
                st.markdown(entry)

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for i, domain in enumerate(s.domains):
            progress_bar.progress(i/total, text=f"Сайт {i+1}/{total}: {domain}")
            contact = s.contacts.get(domain, {"address":"","phone":"","email":f"info@{domain}"})
            theme = s.themes[i] if i < len(s.themes) else s.themes[-1]

            site_cfg = {
                "domain": domain, "brand": brand_from_domain(domain),
                "theme": theme, "language": s.language, "geo": s.geo,
                "address": contact.get("address",""),
                "phone": contact.get("phone",""),
                "email": contact.get("email", f"info@{domain}"),
                "format": fmt,
            }

            log(f"🌐 **Сайт {i+1}/{total}**: `{domain}` — _{theme}_")
            try:
                files = build_one_site(api_key, site_cfg, tpl, fmt, stop_words, seo_kw, extra, log_fn=log)
                prefix = f"{domain}/" if total > 1 else ""
                for fname, content in files.items():
                    zf.writestr(f"{prefix}{fname}", content)
                log(f"✅ `{domain}` — готово!")
            except Exception as e:
                log(f"❌ `{domain}` — помилка: {e}")
            time.sleep(0.5)

    progress_bar.progress(1.0, text="✅ Генерація завершена!")
    zip_buf.seek(0)
    return zip_buf


# ═══════════════════════════════════════
# Wizard UI
# ═══════════════════════════════════════

# Sidebar
with st.sidebar:
    st.markdown("### 🔑 API")
    api_key = st.text_input("Anthropic API Key", type="password", placeholder="sk-ant-...", key="api_key_input")
    if api_key:
        st.session_state.api_key = api_key
        st.success("✅ Ключ збережено")
    st.divider()
    st.caption(f"Модель: claude-sonnet-4-6")
    st.caption(f"Крок: {st.session_state.step}")
    st.divider()
    if st.button("🔄 Почати спочатку", use_container_width=True):
        reset_all()
        st.rerun()

# Header
st.markdown("## 🌐 CleanMeta — Генератор сайтів")

if not TEMPLATE_ZIP_PATH.exists():
    st.error("❌ `template.zip` не знайдено! Покладіть його поряд з `app.py`.")
    st.stop()

# Auto-start
if st.session_state.step == 0:
    bot("👋 **Привіт! Я — CleanMeta генератор сайтів.**\n\nСтворю унікальні сайти з оригінальним контентом через Claude AI.\n\nДавай почнемо! 👇")
    st.session_state.step = 1
    st.rerun()

# Display messages
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Generation in progress
if st.session_state.generating:
    ak = st.session_state.get("api_key","")
    if not ak:
        st.error("❌ API ключ не знайдено!")
        st.session_state.generating = False
    else:
        try:
            zip_buf = run_generation(ak)
            st.session_state.gen_result = zip_buf.getvalue()
            st.session_state.generating = False
            st.success(f"🎉 Готово! {st.session_state.num_sites} сайтів створено.")
            st.download_button("⬇️ Завантажити ZIP", data=st.session_state.gen_result,
                file_name=f"sites_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
                mime="application/zip", type="primary", use_container_width=True)
        except Exception as e:
            st.error(f"❌ Помилка: {e}")
            st.session_state.generating = False
    st.stop()

# Download ready
if st.session_state.gen_result:
    st.success("🎉 Сайти згенеровані!")
    st.download_button("⬇️ Завантажити ZIP", data=st.session_state.gen_result,
        file_name=f"sites_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
        mime="application/zip", type="primary", use_container_width=True)
    if st.button("🆕 Нова генерація"):
        reset_all()
        st.rerun()
    st.stop()

# ─── Step handlers ───
step = st.session_state.step

if step == 1:
    st.markdown("##### 🔧 Крок 1: Формат сайту")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("🐘 PHP", use_container_width=True, key="s1_php"):
            usr("PHP"); st.session_state.format = "php"
            bot("✅ Формат: **PHP**"); st.session_state.step = 2; st.rerun()
    with c2:
        if st.button("🌐 HTML", use_container_width=True, key="s1_html"):
            usr("HTML"); st.session_state.format = "html"
            bot("✅ Формат: **HTML**"); st.session_state.step = 2; st.rerun()

elif step == 2:
    st.markdown("##### 📊 Крок 2: Скільки сайтів потрібно?")
    num = st.number_input("Введіть число (1–200)", min_value=1, max_value=200, value=1, key="s2_num")
    if st.button("Далі ➡️", key="s2_go", use_container_width=True):
        usr(str(num)); st.session_state.num_sites = num
        bot(f"✅ Кількість: **{num}**"); st.session_state.step = 3; st.rerun()

elif step == 3:
    st.markdown("##### 🌍 Крок 3: Вкажіть гео / країну")
    geo = st.text_input("Наприклад: Italia, Deutschland...", key="s3_geo")
    if st.button("Далі ➡️", key="s3_go", use_container_width=True) and geo.strip():
        usr(geo.strip()); st.session_state.geo = geo.strip()
        bot(f"✅ Гео: **{geo.strip()}**"); st.session_state.step = 4; st.rerun()

elif step == 4:
    st.markdown("##### 🗣️ Крок 4: Мова сайту")
    lang = st.selectbox("Оберіть мову", list(LANG_CODES.keys()), key="s4_lang")
    if st.button("Далі ➡️", key="s4_go", use_container_width=True):
        usr(lang); st.session_state.language = lang
        bot(f"✅ Мова: **{lang}**"); st.session_state.step = 5; st.rerun()

elif step == 5:
    n = st.session_state.num_sites
    st.markdown(f"##### 🔗 Крок 5: У вас є свої домени? (потрібно: {n})")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("✅ Так, є домени", use_container_width=True, key="s5_yes"):
            usr("Так, є домени")
            bot(f"📋 Надішліть список доменів.\n\nМожна:\n- по одному в рядку\n- або через кому / пробіл\n\nПотрібно доменів: **{n}**.\n\nКоли закінчите — натисніть «✅ Готово».")
            st.session_state.has_domains = True; st.session_state.step = 51; st.rerun()
    with c2:
        if st.button("⏭️ Немає, пропустити", use_container_width=True, key="s5_no"):
            usr("Пропустити")
            doms = [f"site-{i+1:03d}.example.com" for i in range(n)]
            st.session_state.domains = doms; st.session_state.has_domains = False
            bot(f"✅ Створено {n} тимчасових доменів.")
            st.session_state.step = 6; st.rerun()

elif step == 51:
    need = st.session_state.num_sites
    st.markdown(f"##### 📋 Домени (потрібно: {need})")
    dt = st.text_area("Домени", placeholder="example.com\nsite2.net\nanother.org", height=150, key="s51_area")
    uf = st.file_uploader("Або .txt файл", type=["txt"], key="s51_file")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("✅ Готово", key="s51_done", use_container_width=True):
            text = dt
            if uf: text = uf.read().decode("utf-8", errors="replace")
            doms = parse_domains(text)
            if not doms:
                st.error("❌ Не бачу доменів. Надішліть домени (наприклад: `example.com, site.net`).")
            else:
                if len(doms) < need:
                    for i in range(len(doms), need):
                        doms.append(f"site-{i+1:03d}.example.com")
                    st.warning(f"⚠️ Доменів: {len(parse_domains(text))}, доповнено до {need}.")
                elif len(doms) > need:
                    doms = doms[:need]
                st.session_state.domains = doms
                usr(f"Домени: {', '.join(doms[:5])}{'...' if len(doms)>5 else ''}")
                bot(f"✅ Прийнято. Доменів: **{len(doms)}** (потрібно: {need}). ✅ Доменів достатньо.")
                st.session_state.step = 6; st.rerun()
    with c2:
        if st.button("⏭️ Пропустити", key="s51_skip", use_container_width=True):
            doms = [f"site-{i+1:03d}.example.com" for i in range(need)]
            st.session_state.domains = doms
            usr("Пропустити"); bot(f"✅ Створено {need} тимчасових доменів.")
            st.session_state.step = 6; st.rerun()

elif step == 6:
    bot("📞 **Контакти**: надішліть телефон / адресу / пошту.\n\nМожна надсилати БУДЬ-ЯКИЙ текст (кілька повідомлень або `.txt`) — я витягну контакти.\n\nВаріанти:\n- `domain.com: адреса, +39..., email@...`\n- або просто список контактів без доменів (я розподілю по доменах)\n\nКоли закінчите — натисніть «✅ Готово».")
    st.session_state.step = 61; st.rerun()

elif step == 61:
    st.markdown("##### 📞 Контакти")
    ct = st.text_area("Контактні дані", placeholder="domain.com: Via Roma 10, Milano, +39 02 1234567, info@domain.com", height=150, key="s61_area")
    uf = st.file_uploader("Або .txt файл", type=["txt"], key="s61_file")
    if st.button("✅ Готово", key="s61_done", use_container_width=True):
        text = ct
        if uf: text = uf.read().decode("utf-8", errors="replace")
        if not text.strip():
            st.error("❌ Введіть контактні дані.")
        else:
            contacts = parse_contacts(text, st.session_state.domains)
            st.session_state.contacts = contacts
            usr(f"Контакти надіслано ({len(contacts)} записів)")
            bot("✅ Контакти збережені.")
            st.session_state.step = 7; st.rerun()

elif step == 7:
    st.markdown("##### 📌 Тематика сайтів: що оберете?")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("🧠 Згенерувати різні теми", use_container_width=True, key="s7_gen"):
            usr("Згенерувати теми")
            bot("Ок. Опишіть область / нішу, за якою потрібно згенерувати РІЗНІ теми (за кількістю сайтів).")
            st.session_state.theme_mode = "generate"; st.session_state.step = 71; st.rerun()
    with c2:
        if st.button("📝 Вказати тему вручну", use_container_width=True, key="s7_manual"):
            usr("Вказати вручну")
            bot("Ок. Вкажіть свої теми.\n\nФормат: перелічіть теми через крапку з комою `;`.\nВони будуть розподілені порівну по кількості сайтів.\n\nПриклад: `Forex education; Personal finance basics; Budget planning`")
            st.session_state.theme_mode = "manual"; st.session_state.step = 72; st.rerun()

elif step == 71:
    st.markdown("##### 🧠 Опишіть нішу")
    niche = st.text_input("Ніша / область", placeholder="здорове харчування, фітнес, фінанси...", key="s71_niche")
    if st.button("🧠 Згенерувати", key="s71_go", use_container_width=True) and niche.strip():
        ak = st.session_state.get("api_key","")
        if not ak:
            st.error("❌ Вкажіть API ключ у бічній панелі!")
        else:
            usr(niche.strip())
            with st.spinner("Генерую теми, зачекайте..."):
                try:
                    themes = generate_themes(ak, niche.strip(), st.session_state.num_sites, st.session_state.language)
                    st.session_state.themes = themes
                    preview = "\n".join(f"  {i+1}. {t}" for i,t in enumerate(themes[:10]))
                    if len(themes)>10: preview += f"\n  ... та ще {len(themes)-10}"
                    bot(f"✅ Готово. Згенеровано {len(themes)} тем:\n\n{preview}")
                    st.session_state.step = 8; st.rerun()
                except Exception as e:
                    st.error(f"❌ Помилка: {e}")

elif step == 72:
    st.markdown("##### 📝 Вкажіть теми")
    tt = st.text_area("Теми (через `;`)", placeholder="Yoga studio; CrossFit gym; Pilates", key="s72_area")
    if st.button("✅ Готово", key="s72_done", use_container_width=True) and tt.strip():
        raw = [t.strip() for t in tt.split(";") if t.strip()]
        if not raw:
            st.error("❌ Вкажіть хоча б одну тему.")
        else:
            n = st.session_state.num_sites
            themes = []
            while len(themes) < n: themes.extend(raw)
            themes = themes[:n]
            st.session_state.themes = themes
            usr(f"Теми: {'; '.join(raw)}")
            bot(f"✅ Прийнято {len(raw)} тем, розподілено на {n} сайтів.")
            st.session_state.step = 8; st.rerun()

elif step == 8:
    st.markdown("##### 🔑 Є SEO ключові слова, які потрібно використовувати?")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("✅ Так", use_container_width=True, key="s8_yes"):
            usr("Так"); st.session_state.has_seo = True
            bot("Введіть ключові слова (через кому):")
            st.session_state.step = 81; st.rerun()
    with c2:
        if st.button("❌ Ні", use_container_width=True, key="s8_no"):
            usr("Ні"); st.session_state.has_seo = False
            bot("✅ Без SEO ключових слів.")
            st.session_state.step = 9; st.rerun()

elif step == 81:
    kw = st.text_input("Ключові слова", placeholder="keyword1, keyword2, keyword3", key="s81_kw")
    if st.button("✅ Готово", key="s81_done", use_container_width=True) and kw.strip():
        usr(kw.strip()); st.session_state.seo_keywords = kw.strip()
        bot("✅ Ключові слова збережені.")
        st.session_state.step = 9; st.rerun()

elif step == 9:
    st.markdown("##### 🚫 Є стоп-слова, які НЕ можна використовувати?")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("✅ Так", use_container_width=True, key="s9_yes"):
            usr("Так"); st.session_state.has_stopwords = True
            bot("Введіть стоп-слова (через кому):")
            st.session_state.step = 91; st.rerun()
    with c2:
        if st.button("❌ Ні", use_container_width=True, key="s9_no"):
            usr("Ні"); st.session_state.has_stopwords = False
            bot("✅ Без стоп-слів.")
            st.session_state.step = 10; st.rerun()

elif step == 91:
    sw = st.text_input("Стоп-слова", placeholder="cheap, free, discount, best", key="s91_sw")
    if st.button("✅ Готово", key="s91_done", use_container_width=True) and sw.strip():
        usr(sw.strip()); st.session_state.stop_words = sw.strip()
        bot("✅ Стоп-слова збережені.")
        st.session_state.step = 10; st.rerun()

elif step == 10:
    st.markdown("##### 📋 Останній крок: є додаткові вимоги?")
    st.caption("Якщо немає — натисніть «Ні».")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("✅ Так", use_container_width=True, key="s10_yes"):
            usr("Так"); st.session_state.has_extra = True
            bot("Опишіть додаткові вимоги для сайту:")
            st.session_state.step = 101; st.rerun()
    with c2:
        if st.button("❌ Ні", use_container_width=True, key="s10_no"):
            usr("Ні"); st.session_state.has_extra = False
            bot("✅ Чудово! Все зібрано. Перевірте підсумок нижче і запускайте генерацію! 🚀")
            st.session_state.step = 11; st.rerun()

elif step == 101:
    ex = st.text_area("Додаткові вимоги", placeholder="Формальний тон, FAQ секція, ...", key="s101_ex")
    if st.button("✅ Готово", key="s101_done", use_container_width=True) and ex.strip():
        usr(ex.strip()); st.session_state.extra_requirements = ex.strip()
        bot("✅ Вимоги збережені. Перевірте підсумок і запускайте! 🚀")
        st.session_state.step = 11; st.rerun()

elif step == 11:
    # Summary
    s = st.session_state
    st.markdown("---")
    st.markdown("### 📋 Підсумок")
    st.markdown(f"**Формат:** {s.format.upper()}")
    st.markdown(f"**Кількість сайтів:** {s.num_sites}")
    st.markdown(f"**Гео:** {s.geo}")
    st.markdown(f"**Мова:** {s.language}")
    doms_preview = ', '.join(s.domains[:5])
    if len(s.domains)>5: doms_preview += f"... (+{len(s.domains)-5})"
    st.markdown(f"**Домени:** {doms_preview}")
    st.markdown(f"**Контакти:** {len(s.contacts)} записів")
    uniq_themes = len(set(s.themes))
    st.markdown(f"**Теми:** {uniq_themes} унікальних")
    if s.has_seo: st.markdown(f"**SEO ключі:** {s.seo_keywords[:80]}")
    if s.has_stopwords: st.markdown(f"**Стоп-слова:** {s.stop_words[:80]}")
    if s.has_extra: st.markdown(f"**Додатково:** {s.extra_requirements[:80]}")
    st.markdown("---")

    est = s.num_sites * 2
    st.info(f"⏱️ Орієнтовний час: ~{est} хв ({s.num_sites} сайтів × 9 сторінок)")

    ak = st.session_state.get("api_key","")
    if not ak:
        st.error("⚠️ Вкажіть Anthropic API ключ у бічній панелі!")
    else:
        if st.button("🚀 ГЕНЕРУВАТИ САЙТИ", type="primary", use_container_width=True, key="s11_gen"):
            st.session_state.generating = True
            st.rerun()
