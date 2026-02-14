FROM python:3.10-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY auth_service/requirements.txt /app/auth_service/requirements.txt
RUN pip install --no-cache-dir -r /app/auth_service/requirements.txt

COPY auth_service /app/auth_service
COPY shared /app/shared

EXPOSE 5002

CMD ["uvicorn", "auth_service.app:app", "--host", "0.0.0.0", "--port", "5002", "--no-access-log"]
