# Разработка и Windows-сборка

Проверенная среда: Windows x64, Python 3.14, версии из `requirements.txt`.
Готовый ZIP работает без установленного Python. Другие ОС пока не проверены.

```powershell
py -3.14 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Локальный клиент — модифицированный Albion Data Client. Исходники поставляются в
`vendor/albion-data-client`, лицензия исходного проекта сохранена. Нужен Go 1.27.1:

```powershell
New-Item -ItemType Directory -Force tools/albion-data-client, build | Out-Null
$env:CGO_ENABLED='0'
Push-Location vendor/albion-data-client
go build -trimpath -o ../../build/albioncraft-data-client.exe albioncraft-local.go
go list -deps -f '{{with .Module}}{{.Dir}}{{end}}' albioncraft-local.go | Set-Content ../../build/go-modules.txt
Pop-Location
.venv\Scripts\python.exe scripts/collect_licenses.py
.venv\Scripts\python.exe scripts/prepare_brand.py
.venv\Scripts\python.exe -m PyInstaller AlbionCraft.spec --noconfirm
.venv\Scripts\python.exe scripts/package_release.py
```

Сборка использует явный список файлов. Кэш, базы персонажа, настройки, логи,
установщики и экспериментальные скриншоты не попадают в исходный ZIP.
Npcap скачивается отдельно по действию пользователя и не распространяется в сборке.

Проверка собранного EXE (изолированный временный профиль, без сетевых запросов):

```powershell
$report=Join-Path $PWD 'build/frozen-check.json'
$quotedReport='"'+$report+'"'
$p = Start-Process -FilePath dist/AlbionCraft/AlbionCraft.exe -ArgumentList '--smoke-test', $quotedReport -WindowStyle Hidden -Wait -PassThru
Get-Content build/frozen-check.json
if ($p.ExitCode -ne 0) { throw 'Release smoke test failed' }
```

Проверяется запуск окна, загрузка игровых данных, MILP-решатель,
OCR, отдельные процессы сканирования, рекомендаций, ходки и свободной славы,
острова, бюджет всей операции, резервное копирование, диагностика, русский OCR
бонусов и раздельные папки серверов. Модель Cyrillic PP-OCRv5 включена в
`app/assets/ocr`; источник и SHA256 находятся в её README. Результат проверки дополняет
юнит-тесты; проверка на этом компьютере не заменяет проверку на чистой машине.

## Данные при разработке

Из исходников профиль остаётся рядом с кодом. Для проверки чистого первого запуска:

```powershell
$env:ALBIONCRAFT_DATA_DIR = "$env:TEMP/AlbionCraft-demo"
.venv\Scripts\python.exe -m app.main
```

Не включайте содержимое этой папки в Git. Файлы в `research` — фиксированный
снимок игровых данных. Изменения механик игры требуют обновления снимков и
проверки формул. Не заменяйте неизвестные цены или объёмы нулями.
