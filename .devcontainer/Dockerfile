FROM python:3.11.3-slim-bullseye

ENV PYTHONUNBUFFERED True
RUN apt-get update
RUN apt-get install git wkhtmltopdf -y

COPY requirements.txt .

RUN python -m venv section_extraction_venv
ENV PATH="/section_extraction_venv/bin:$PATH"
RUN . /pymupdf-venv/bin/activate

RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

CMD ["bash"]
