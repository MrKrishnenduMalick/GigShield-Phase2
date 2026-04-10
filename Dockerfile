FROM python:3.10

WORKDIR /app

COPY api/ /app

RUN pip install --no-cache-dir -r requirements.txt

CMD ["uvicorn", "index:app", "--host", "0.0.0.0", "--port", "10000"]
