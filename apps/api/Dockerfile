FROM python:3.12-slim
WORKDIR /app
COPY apps/api/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY apps/api/app ./app
COPY models/deposit-quantile-v2.joblib ./models/deposit-quantile-v2.joblib
COPY models/deposit-quantile-v2.manifest.json ./models/deposit-quantile-v2.manifest.json
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEPOSIT_MODEL_PATH=/app/models/deposit-quantile-v2.joblib \
    REQUIRE_DEPOSIT_MODEL=true
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD python -c "import json,urllib.request; data=json.load(urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=5)); assert data['deposit_model']['status'] == 'ready'; assert data['deposit_model']['integrity'] == 'verified'"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
