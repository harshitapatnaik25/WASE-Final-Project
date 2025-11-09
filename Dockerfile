FROM python:3.11-slim

WORKDIR /app


COPY requirements.txt .

ENV PYTHONIOENCODING=UTF-8


RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Expose no ports (Slack uses outgoing connections)
EXPOSE 3000

CMD ["python", "app.py"]
