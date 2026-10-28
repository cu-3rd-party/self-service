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
пока не установлено отсутствие работающего apply. Удаления и замены выполняются автоматически из проверенного master.

## Cloudflare DNS и ingress

В `/etc/cu3rd-self-service/cloudflare.env` (root, chmod 600):

```sh
CLOUDFLARE_API_TOKEN='<token>'
TF_VAR_cloudflare_zone_id='<zone-id-cu3rd.ru>'
```

Токен: Zone → DNS → Edit, ограниченный cu3rd.ru. Zone → Zone → Read нужен только
для автоматического обнаружения Zone ID, если он ещё неизвестен. Привилегированные
ключи не записываются в Git, Variables или Secrets приложений. После изменения
установить актуальный `ops/reconcile.sh` в `/opt/cu3rd-self-service/reconcile.sh`,
удалить `/var/lib/cu3rd-self-service/applied-revision` и запустить service, чтобы
не ждать часовой проверки неизменившейся ревизии.

DNS создаётся OpenTofu, маршруты — Argo CD, сертификаты — cert-manager. Выпуск
сертификата ждёт распространения DNS и доступности HTTP-01 на внешнем порту 80.
Проверка: `kubectl -n <namespace> get ingress,certificate,challenge`.
Новые ingress без настроенной Cloudflare зоны останавливают plan до apply.
Наличие записи в Cloudflare проверяется обычным plan/create; существующие записи
импортируются вручную после проверки владельца, без allow-overwrite.

## Декларативное удаление

`check-plan.py` печатает количества create/update/delete/replacement, но не запрещает
удаление. БД, роли, бакеты, пользователи и namespaces не имеют `prevent_destroy`.
S3 bucket/user используют `force_destroy`; Argo Applications — foreground finalizer,
PVC не имеют keep/Delete=false. Ресурсы вне self-service state и его Argo Applications
не затрагиваются. После обновления ops установите скрипт отдельно в /opt, как обычно.

`cleanup-tls.py` запускается после apply и на каждом тике таймера, даже при неизменном
master. В namespaces self-service он удаляет только cert-manager TLS Secrets, у которых
уже нет Certificate и ссылок из Ingress. Это необходимо, потому что общий cert-manager
не включает certificate-owner-ref. Namespace deletion самостоятельно удаляет все Secrets.

Для сценария двух PR сначала убедитесь, что первая ревизия появилась в
`/var/lib/cu3rd-self-service/applied-revision` и ресурсы действительно удалены, затем
возвращайте YAML. Таймер обрабатывает актуальный master и не воспроизводит каждый
промежуточный commit. Продолжают действовать блокировка state и review Owners.
