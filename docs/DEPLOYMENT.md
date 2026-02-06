# Deployment Guide

## Docker Deployment

### Local Development

```bash
# Start all services with hot reload
docker-compose up -d

# View logs
docker-compose logs -f backend

# Stop services
docker-compose down
```

### Production Deployment

1. **Build production images:**

```bash
docker build -t lighting-backend:latest ./backend
docker build -t lighting-frontend:latest ./frontend
```

2. **Push to registry:**

```bash
docker tag lighting-backend:latest your-registry/lighting-backend:latest
docker push your-registry/lighting-backend:latest

docker tag lighting-frontend:latest your-registry/lighting-frontend:latest
docker push your-registry/lighting-frontend:latest
```

3. **Deploy with production compose:**

```yaml
# docker-compose.prod.yml
version: '3.8'

services:
  backend:
    image: your-registry/lighting-backend:latest
    environment:
      - DATABASE_URL=postgresql://user:pass@db-host/lighting_db
      - DEBUG=false
      - SECRET_KEY=${SECRET_KEY}
    deploy:
      replicas: 2
      resources:
        limits:
          cpus: '1'
          memory: 1G

  frontend:
    image: your-registry/lighting-frontend:latest
    deploy:
      replicas: 2
```

## Kubernetes Deployment

### Prerequisites

- Kubernetes cluster
- kubectl configured
- Helm (optional)

### Basic Deployment

```yaml
# k8s/backend-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: lighting-backend
spec:
  replicas: 2
  selector:
    matchLabels:
      app: lighting-backend
  template:
    metadata:
      labels:
        app: lighting-backend
    spec:
      containers:
      - name: backend
        image: your-registry/lighting-backend:latest
        ports:
        - containerPort: 8000
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: lighting-secrets
              key: database-url
        resources:
          requests:
            memory: "512Mi"
            cpu: "250m"
          limits:
            memory: "1Gi"
            cpu: "1"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5
```

### Service

```yaml
# k8s/backend-service.yaml
apiVersion: v1
kind: Service
metadata:
  name: lighting-backend
spec:
  selector:
    app: lighting-backend
  ports:
  - port: 8000
    targetPort: 8000
  type: ClusterIP
```

### Ingress

```yaml
# k8s/ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: lighting-ingress
  annotations:
    nginx.ingress.kubernetes.io/websocket-services: "lighting-backend"
spec:
  rules:
  - host: lighting.example.com
    http:
      paths:
      - path: /api
        pathType: Prefix
        backend:
          service:
            name: lighting-backend
            port:
              number: 8000
      - path: /ws
        pathType: Prefix
        backend:
          service:
            name: lighting-backend
            port:
              number: 8000
      - path: /
        pathType: Prefix
        backend:
          service:
            name: lighting-frontend
            port:
              number: 80
```

## Database Migrations

```bash
# Generate migration
cd backend
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback
alembic downgrade -1
```

## SSL/TLS Configuration

### With Let's Encrypt (Certbot)

```bash
# Install certbot
apt install certbot python3-certbot-nginx

# Obtain certificate
certbot --nginx -d lighting.example.com

# Auto-renewal
certbot renew --dry-run
```

### Nginx SSL Configuration

```nginx
server {
    listen 443 ssl http2;
    server_name lighting.example.com;

    ssl_certificate /etc/letsencrypt/live/lighting.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/lighting.example.com/privkey.pem;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256;
    ssl_prefer_server_ciphers off;

    location / {
        proxy_pass http://frontend;
    }

    location /api {
        proxy_pass http://backend:8000;
    }

    location /ws {
        proxy_pass http://backend:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

## Monitoring

### Prometheus Metrics

Add to backend for metrics:

```python
from prometheus_client import Counter, Histogram, generate_latest

requests_total = Counter('requests_total', 'Total requests')
request_latency = Histogram('request_latency_seconds', 'Request latency')

@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type="text/plain")
```

### Health Checks

- Backend: `GET /health`
- Frontend: `GET /health`

## Backup and Recovery

### Database Backup

```bash
# Backup
pg_dump -h localhost -U postgres lighting_db > backup.sql

# Restore
psql -h localhost -U postgres lighting_db < backup.sql
```

### Automated Backups

```bash
# Cron job for daily backups
0 2 * * * pg_dump -h localhost -U postgres lighting_db | gzip > /backups/lighting_$(date +\%Y\%m\%d).sql.gz
```

## Troubleshooting

### Common Issues

1. **WebSocket connection fails:**
   - Check Nginx websocket configuration
   - Verify firewall allows WS connections

2. **Database connection errors:**
   - Verify DATABASE_URL environment variable
   - Check PostgreSQL is running

3. **Audio streaming latency:**
   - Reduce chunk size
   - Check network bandwidth
   - Use local processing when possible
