FROM python:3.10

WORKDIR /app

COPY . /app

RUN pip install --no-cache-dir -r api/requirements.txt

CMD ["uvicorn", "api.index:app", "--host", "0.0.0.0", "--port", "10000"]
