"""
Gunicorn — оптимизирован под высокий трафик.
Формула воркеров: (2 × CPU) + 1
"""
import multiprocessing

# В Docker лучше TCP, за Nginx можно unix-сокет
bind = "0.0.0.0:8000"
# bind = "unix:/tmp/gunicorn.sock"   # раскомментировать для Nginx на том же хосте

workers          = multiprocessing.cpu_count() * 2 + 1
worker_class     = "gthread"    # потоковые воркеры — баланс CPU/IO
threads          = 4
worker_connections = 1000

timeout          = 30
graceful_timeout = 30
keepalive        = 5

accesslog = "-"
errorlog  = "-"
loglevel  = "info"

limit_request_line   = 8190
limit_request_fields = 100

# Периодический перезапуск воркеров — защита от утечек памяти
max_requests        = 2000
max_requests_jitter = 200

# Preload — быстрый форк воркеров
preload_app = True
