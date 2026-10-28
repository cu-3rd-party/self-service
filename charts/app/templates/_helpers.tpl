{{- define "app.labels" -}}
app.kubernetes.io/name: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{ include "app.identity" . }}
{{- end }}
{{- define "app.selector" -}}
app.kubernetes.io/name: {{ .Release.Name }}
{{- end }}

{{- define "app.identity" -}}
{{- with .Values.selfService }}
cu3rd.ru/managed-by: self-service
cu3rd.ru/project: {{ .project | quote }}
cu3rd.ru/env: {{ .env | quote }}
cu3rd.ru/application: {{ .application | quote }}
{{- end }}
{{- end }}
