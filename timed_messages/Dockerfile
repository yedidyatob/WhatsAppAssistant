FROM python:3.10-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY timed_messages/requirements.txt /app/timed_messages/requirements.txt
RUN pip install --no-cache-dir -r /app/timed_messages/requirements.txt

COPY timed_messages /app/timed_messages
COPY shared /app/shared

RUN chmod +x /app/timed_messages/entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/app/timed_messages/entrypoint.sh"]
CMD ["uvicorn", "timed_messages.app:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
