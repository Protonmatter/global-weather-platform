# Production builds MUST override BASE_IMAGE with an internally mirrored, digest-pinned image.
ARG BASE_IMAGE=python:3.12-slim
FROM ${BASE_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    WEATHER_ENVIRONMENT=production

RUN useradd --create-home --uid 10001 weather
WORKDIR /app

# The runtime user cannot write to /app; mount persistent storage here in production.
ENV WEATHER_DATA_DIR=/var/lib/weather
RUN mkdir -p /var/lib/weather && chown weather:weather /var/lib/weather

# The CI workflow creates this wheelhouse from the approved internal package mirror.
COPY .wheelhouse /wheelhouse
RUN python -m pip install \
      --no-index \
      --find-links=/wheelhouse \
      --no-cache-dir \
      global-weather-platform \
    && rm -rf /wheelhouse

USER 10001
EXPOSE 8080
ENTRYPOINT ["uvicorn", "weather_platform.api.main:app", "--host", "0.0.0.0", "--port", "8080"]
