# Этап B. Сравнение протоколов и поддержка в установленной сборке curl

Проверено фактически командой `curl --version`:

```
curl 8.13.0 (Windows) libcurl/8.13.0 Schannel zlib/1.3.1 WinIDN
Release-Date: 2025-04-02
Protocols: dict file ftp ftps http https imap imaps ipfs ipns mqtt pop3 pop3s smb smbs smtp smtps telnet tftp ws wss
Features: alt-svc AsynchDNS HSTS HTTPS-proxy IDN IPv6 Kerberos Largefile libz NTLM SPNEGO SSL SSPI threadsafe Unicode UnixSockets
```

| Протокол | Типичная задача | Шифрованный вариант | Поддерживается вашей сборкой |
|---|---|---|---|
| HTTP | Запросы к REST API: получить список операций (GET), создать (POST), изменить (PUT/PATCH), удалить (DELETE), посмотреть заголовки ответа | HTTPS | да (http, https) |
| FTP | Передача файлов: скачать выгрузку с ftp-сервера или загрузить отчёт; в curl — команды скачивания/загрузки файла | FTPS | да (ftp, ftps) |
| SMTP | Отправка почты: письмо с результатами расчёта или ссылкой на отчёт | SMTPS | да (smtp, smtps) |

Все протоколы, которые перечисляет установленная сборка:

`dict, file, ftp, ftps, http, https, imap, imaps, ipfs, ipns, mqtt, pop3, pop3s, smb, smbs, smtp, smtps, telnet, tftp, ws, wss`

## Пояснения

- `curl --version` печатает строку `Protocols:` со списком протоколов, которые реально включены в сборку. Официальный manual curl отдельно предупреждает, что набор зависит от сборки, поэтому проверять нужно свою.
- Шифрованные варианты (HTTPS, FTPS, SMTPS) — это те же протоколы поверх TLS. Для curl это отдельные имена в списке протоколов, а не «галочка» в настройках.
- Для лабораторной работы реально использовался только HTTP: `GET/POST/PUT/PATCH/DELETE` к `http://127.0.0.1:8000/api/transactions`. К внешним FTP- и SMTP-серверам подключения не выполнялись — это и не требуется.

## Чем curl отличается от библиотеки requests

- `curl` — отдельная программа командной строки: работает без Python, умеет HTTP, FTP, SMTP и другие протоколы, показывает заголовки, коды ответа и редиректы «как есть». Удобен для диагностики: видно, что именно вернул сервер.
- `requests` — библиотека Python: работает только по HTTP(S), зато ответ сразу превращается в объекты Python (`.json()`, `.status_code`), и его удобно обрабатывать в коде конвейера.
- В конвейере этой работы оба инструмента дополняют друг друга: curl — ручная проверка API (этап A), requests — программная загрузка данных (этап C).

_Файл сформирован автоматически: `protocols.py`._
