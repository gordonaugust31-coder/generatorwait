# 🌐 CleanMeta — Генератор сайтів

Покроковий чат-візард для масової генерації унікальних PHP/HTML сайтів через Claude AI.

## Можливості

- **Batch-генерація**: від 1 до 200 сайтів за раз
- **Чат-візард**: покрокове введення всіх параметрів
- **Унікальний контент**: кожна сторінка генерується через Claude API
- **9 сторінок на сайт**: головна, каталог, фічі, about, контакт, privacy, cookie, terms, 404
- **Авто-навігація**: slug'и та назви меню генеруються під мову/нішу
- **30+ мов**
- **SEO**: ключові слова, мета-теги, JSON-LD, sitemap
- **Стоп-слова**: фільтрація небажаних слів

## Кроки візарда

1. Формат (PHP / HTML)
2. Кількість сайтів (1–200)
3. Гео / країна
4. Мова
5. Домени (свої або автогенерація)
6. Контакти (телефон, адреса, пошта)
7. Тематика (AI-генерація або вручну)
8. SEO ключові слова
9. Стоп-слова
10. Додаткові вимоги

## Деплой на Streamlit Cloud

```
1. Створіть репозиторій на GitHub
2. Завантажте файли: app.py, requirements.txt, template.zip
3. Зайдіть на share.streamlit.io
4. Вкажіть репо → app.py
5. Deploy!
```

## Локальний запуск

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Файли

```
app.py          — Streamlit додаток (візард + генерація)
template.zip    — шаблон сайту (PHP/HTML/CSS/JS/images)
requirements.txt — залежності
```

## На виході

Для 1 сайту — ZIP з файлами:
```
index.php, [listing].php, [feature].php, [about].php,
contact.php, privacy-policy.php, cookie-policy.php,
terms-of-service.php, 404.html,
sitemap.xml, robots.txt, .htaccess,
css/, js/, images/, favicons
```

Для N сайтів — ZIP з папками по доменах:
```
domain1.com/index.php, ...
domain2.com/index.php, ...
```
