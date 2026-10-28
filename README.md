# cu3rd self-service

Приложения и ресурсы cu3rd описываются в `projects/*.yaml`. Основная ветка — **master**.
OpenTofu создаёт namespace, квоты, NetworkPolicy, Postgres, S3 и Argo CD Application.
Argo CD разворачивает приложения из общего чарта. Инфраструктура homelab остаётся отдельно.

## Завести приложение

1. Скопируйте `examples/telegram-bot.yaml` в `projects/<имя>.yaml`, укажите существующую
   команду Forgejo, репозиторий и опубликованный образ. Откройте PR и получите ревью платформы.
2. В репозитории приложения добавьте Settings → Actions → Secrets → `TELEGRAM_BOT_TOKEN`.
   В Settings → Actions → Variables добавьте `TELEGRAM_BOT_NAME`.
3. Добавьте workflow из `examples/deploy-workflow.yaml`. Платформа выдаёт
   `SELF_SERVICE_DELIVERY_TOKEN`: отдельный токен бота с доступом только к этому self-service.
   Он может создавать ветки и PR, но не пушить/мержить защищённый `master`.
4. После публикации образа запустите delivery с его тегом. Workflow откроет PR,
   включающий тег, обычные переменные и зашифрованные секреты. После ревью и merge
   процесс на nxs применит master (обычно в течение минуты), затем Argo CD обновит под.

```yaml
name: telegram-bot
team: bot-devs
envs:
  dev:
    zone: nxs
    postgres:
      enabled: true
      targetEnv: DB_CONNSTRING
      format: url
    s3:
      enabled: true
      targetEnvPrefix: S3__
      quotaBytes: 2147483648
    apps:
      bot:
        repo: cu3rd/my-bot
        image: git.cu3rd.ru/cu3rd/my-bot
        tag: initial
        port: null
        secrets:
          TELEGRAM_BOT_TOKEN: TELEGRAM_BOT_TOKEN
        variables:
          TELEGRAM_BOT_NAME: TELEGRAM_BOT_NAME
```

Слева — имя env внутри контейнера, справа — имя Actions Secret/Variable. Имена справа
пишутся uppercase. Можно переименовывать, например `Bot__Token: TELEGRAM_BOT_TOKEN`.
Передаются только перечисленные значения. Необъявленные ключи CI не копируются в приложение.
При отсутствии/пустом значении workflow завершается ошибкой, сохраняя предыдущий деплой.
Многострочные значения поддерживаются. Пока нет первой доставки, приложения с mappings
не запускаются; заказанные ресурсы могут быть созданы заранее.

Секреты шифруются публичным сертификатом `certs/sealed-secrets.pem` в strict scope:
namespace `cu3rd-<проект>-<env>`, Secret `<проект>-<env>-<app>-env`.
Открытые токены не записываются в Git, аргументы команд или логи. JSON контекста secrets
обрабатывается доверенным delivery-скриптом в памяти; используйте проверенную версию action.
Изменение доставки меняет аннотацию pod template, вызывая rollout. Чтобы заменить токен
или переменную, обновите Actions Settings и повторно запустите delivery. Изменение настроек
Forgejo само по себе не запускает workflow.

## Публикация HTTP-приложения

В каждом окружении у приложения задайте список `ingress`:

```yaml
envs:
  dev:
    zone: nxs
    apps:
      backend:
        repo: cu3rd/my-app
        image: git.cu3rd.ru/cu3rd/my-app
        tag: initial
        ingress:
          - domain: testcontainer.dev.cu3rd.ru
            targetPort: 8080
  prod:
    zone: grm
    apps:
      backend:
        repo: cu3rd/my-app
        image: git.cu3rd.ru/cu3rd/my-app
        tag: initial
        ingress:
          - domain: testcontainer.cu3rd.ru
            targetPort: 8080
```

После merge в master платформа создаёт:

1. Cloudflare A-запись: `nxs` → `85.192.48.255`, `grm` → `109.120.137.209`.
   Режим DNS only (`proxied: false`), TTL 120 секунд. Один домен — одна DNS-запись,
   даже если несколько приложений делят его по путям.
2. Service с портом **80**, направленным на `targetPort` контейнера (1024–65535).
3. Ingress класса Traefik, сертификат Let's Encrypt через cert-manager HTTP-01,
   перенаправление HTTP → HTTPS. Внешние порты: **80 и 443**, HTTPS завершается на Traefik;
   от Traefik до приложения идёт HTTP. Cloudflare не терминирует TLS.

`port` можно не указывать: основной порт выводится из первого `targetPort`.
Для нескольких доменов/портов добавьте элементы списка. Необязательный `paths: [/api]`
ограничивает маршрут; по умолчанию `[/]`. Один домен может делиться между приложениями
в одном окружении по разным путям. Дубли домен/путь и использование одного домена
разными проектами или окружениями отклоняются. Wildcard-домены не поддерживаются.

Старый синтаксис `host`/`paths`/`port` поддерживается, но нельзя смешивать его с
`ingress` у одного приложения. Для существующих DNS-записей требуется проверка и
`tofu import`; платформа не перехватывает их автоматически.

Полный пример: `examples/ingress.yaml`. Ключ Cloudflare хранится только на nxs;
его не нужно передавать репозиториям приложений. Для смены IP узлов платформа
обновляет `zone_addresses` в `dns.tf`. Удаление DNS-записи пока тоже требует
отдельной операции платформы: общий запрет destructive plans остаётся в силе.

## Автоматически создаваемые переменные

| Опция | Переменные контейнера |
|---|---|
| Postgres `targetEnv: DB_CONNSTRING`, `format: url` | `DB_CONNSTRING=postgresql://…` |
| Postgres `format: npgsql` | `Host=…;Port=5432;Database=…;Username=…;Password=…;No Reset On Close=true` |
| S3 `targetEnvPrefix: S3__` | `S3__ACCESS_KEY`, `S3__SECRET_KEY`, `S3__URL`, `S3__BUCKET_NAME` |

Postgres — существующий кластер `pg-grm` и transaction pooler, независимо от зоны пода.
S3 — RustFS, path-style, region `us-east-1`. Квота S3 задаётся в байтах. Доступы общие
для приложений одного окружения; переменные ресурсов нельзя перекрыть mappings.
Системные пароли лежат в Kubernetes Secrets и зашифрованном OpenTofu state, не в Git
и не в Forgejo Secrets. Из интерфейса Forgejo их посмотреть нельзя.

## Ограничения и безопасность

- Новые namespaces имеют префикс `cu3rd-`, restricted Pod Security, отдельные квоты и
  NetworkPolicy. По умолчанию pod работает UID/GID 10001 без service-account token;
  образ должен поддерживать запуск без root. HTTP-порт: 1024–65535.
- Между приложениями разрешён доступ внутри своего namespace. Разрешены DNS, Postgres,
  S3 и внешний HTTP(S); private ranges и IP узлов исключены из internet egress.
- Для каждого окружения создаётся отдельный Argo AppProject с единственным namespace.
- Actions проверяет YAML и тесты без ключей инфраструктуры. Привилегированный apply
  выполняется отдельным systemd-процессом на nxs, а не общим DinD-раннером.
- В первой версии apply использует административный kubeconfig и доступы Postgres/S3
  из root-only файлов на nxs. Любые изменения master — доверенный административный код:
  нужны защита ветки, обязательное ревью Owners и запрет прямого push.
- `prevent_destroy` защищает данные, дополнительная проверка плана запрещает **любые**
  удаления/замены, в том числе удаление блока модуля. Удаление проекта/БД требует
  отдельной операции платформы после бэкапа. Удаление app сейчас тоже блокируется.
- Ключи CI не предоставляются PR. Не запускайте delivery из PR/pull_request_target.
- В первой версии `team` документирует владельца; автоматической выдачи Forgejo/RBAC
  прав и входа в Grafana пока нет. Права выдаёт платформа.
- Existing apps из homelab пока не импортированы: миграция отдельным PR с проверкой
  имён, паролей и отключением прежнего контроллера. Импорт нельзя делать вслепую.

Подробности эксплуатации и восстановления: [docs/operations.md](docs/operations.md).
