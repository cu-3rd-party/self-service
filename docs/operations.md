# Эксплуатация

`ops/reconcile.sh` устанавливается отдельно в `/opt/cu3rd-self-service/reconcile.sh`.
Таймер запускает его раз в минуту; процесс читает только `origin/master`.
Повторная проверка drift — раз в час. Чарт привязан к SHA применяемого commit.
Сам процесс не обновляет свою установленную копию: изменения ops проходят отдельно.

На nxs:

```sh
systemctl status cu3rd-self-service.timer cu3rd-self-service.service
journalctl -u cu3rd-self-service.service -n 100 --no-pager
systemctl start cu3rd-self-service.service
cat /var/lib/cu3rd-self-service/applied-revision
kubectl -n argocd get applications | grep cu3rd
```

- `/etc/cu3rd-self-service/runtime.env`: root-only пароли и ключ шифрования.
- `/etc/cu3rd-self-service/backend.hcl`: S3 backend, native lockfile, versioned bucket.
- `/root/k8s/keys/cu3rd-self-service-runtime.env`: резервная копия ключа на том же хосте.
- `/opt/cu3rd-self-service/repo`: checkout; `.terraform/` содержит метаданные backend,
  поэтому весь каталог закрыт от посторонних пользователей.
- `/var/lib/cu3rd-self-service`: статус и зашифрованный временный план.

Ключ шифрования необходимо отдельно сохранить вне nxs. Версионирование state защищает
от перезаписи, но не заменяет независимую резервную копию RustFS и ключа. Без ключа
восстановить state невозможно. После ротации postgres/S3 admin обновите runtime.env.

Бэкенд использует отдельного S3-пользователя, ограниченного state bucket. Доступ к
RustFS admin и Postgres superuser нужен только процессу apply. Postgres подключается
к ClusterIP сервиса `pg-grm-rw`, TLS require; клиентские URL направлены в pooler.

В PR выполняются schema/semantic checks и unit tests. Привилегированный tofu plan
не запускается на коде PR. Полный план доступен в журнале apply после merge; plaintext
JSON плана передаётся проверке через pipe и не сохраняется. Sensitive значения скрыты
провайдерами, state и saved plans обязательно шифруются AES-GCM/PBKDF2.

## Токен доставки

Создать отдельного служебного пользователя и дать write-доступ **только** к self-service.
Выдать repository-scoped токен `write:repository` + `write:issue`, сохранить его в
Actions Secret `SELF_SERVICE_DELIVERY_TOKEN` репозитория приложения. Пользователь
не должен входить в Owners/merge whitelist. Не используйте org-wide admin/CI токен.
Для private source repository репозиторий self-service не требует доступа к его исходникам.

Проверка `SOURCE_REPOSITORY` предотвращает ошибки настройки; она не является криптографическим
доказательством происхождения PR: токен можно использовать вне workflow. Поэтому каждый
PR проверяет Owners; автослияние доставок не включено. Для автоматического merge понадобится
проверка подписи/Actions OIDC и соответствия repo → project → paths на стороне платформы.

## Восстановление/откат

Остановить timer, сохранить текущие state и ключ, вернуть конфигурацию отдельным revert PR.
Не подменять state старой версией без проверки реальных ресурсов. Не удалять lockfile,
пока не установлено отсутствие работающего apply. Обычные удаления блокируются даже
после удаления `prevent_destroy` из конфигурации; maintenance выполняется вручную
командой платформы после отдельного review и backup.
