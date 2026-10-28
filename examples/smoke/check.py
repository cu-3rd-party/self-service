"""Integration probe. Logs only booleans/status, never credentials."""
import os
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
import boto3
from botocore.config import Config
import psycopg

ready = False
for attempt in range(60):
    try:
        assert os.environ['SMOKE_TOKEN'] == 'self-service-smoke-secret'
        assert os.environ['SMOKE_NAME'] == 'self-service-smoke-bot'
        with psycopg.connect(os.environ['DB_CONNSTRING'], connect_timeout=10) as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT current_database()')
                assert cur.fetchone()[0] == 'platform_smoke_dev'
        s3 = boto3.client('s3', endpoint_url=os.environ['S3__URL'],
            aws_access_key_id=os.environ['S3__ACCESS_KEY'],
            aws_secret_access_key=os.environ['S3__SECRET_KEY'],
            region_name='us-east-1', config=Config(s3={'addressing_style': 'path'}))
        bucket = os.environ['S3__BUCKET_NAME']
        s3.put_object(Bucket=bucket, Key='smoke-check', Body=b'passed')
        assert s3.get_object(Bucket=bucket, Key='smoke-check')['Body'].read() == b'passed'
        s3.delete_object(Bucket=bucket, Key='smoke-check')
        ready = True
        print('PASS: Actions Secret, Actions Variable, PostgreSQL query, S3 put/get/delete')
        break
    except Exception as exc:
        print('Waiting for dependencies:', type(exc).__name__)
        time.sleep(5)
if not ready:
    raise SystemExit('Smoke integration failed; inspect dependencies without printing credentials')
class Health(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'self-service smoke passed\n')
    def log_message(self, *_):
        pass
HTTPServer(('0.0.0.0', 8080), Health).serve_forever()
