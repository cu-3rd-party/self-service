FROM python:3.12-alpine
RUN pip install --no-cache-dir 'psycopg[binary]==3.2.13' 'boto3==1.40.61'
COPY check.py /app/check.py
USER 10001:10001
CMD ["python", "-u", "/app/check.py"]
