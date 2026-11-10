{{- define "vm.labels" -}}
app.kubernetes.io/name: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- with .Values.selfService }}
cu3rd.ru/managed-by: self-service
cu3rd.ru/project: {{ .project | quote }}
cu3rd.ru/env: {{ .env | quote }}
cu3rd.ru/application: {{ .application | quote }}
{{- end }}
{{- end }}
