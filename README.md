# Predicción de demanda energética en Colombia

Este proyecto pronostica la demanda diaria de energía eléctrica de Colombia (Sistema Interconectado Nacional, SIN) para el día siguiente. La única entrada es el historial de demanda que publica XM, de 2000 a 2023. La idea fue ver hasta dónde se podía llegar con ese historial. En 2022 y 2023, años que el modelo no vio, el error promedio fue de 1,30 %.

El proyecto tiene cinco partes:

- **Componente de datos:** lee los 24 archivos anuales con los [datos de demanda del SIN](#ref-1), los revisa y los une en una serie de 8.765 días.
- **Componente de machine learning:** calcula variables a partir del historial, entrena y compara modelos y guarda cada experimento en MLflow. El modelo en uso es un `HistGradientBoostingRegressor` que predice cuánto cambia la demanda frente al mismo día de la semana anterior.
- **Servicio de predicción:** una API en FastAPI genera el pronóstico de una fecha y lo guarda en PostgreSQL con la demanda real de ese día.
- **Aplicación web:** una interfaz en React, en español e inglés, para pedir pronósticos y compararlos con la demanda real.
- **Informe de Power BI:** cinco páginas sobre el sistema eléctrico. Ponen la demanda junto al [precio de bolsa, los embalses y los aportes hídricos](#ref-2), las [fases de El Niño y La Niña](#ref-3) y los [festivos de Colombia](#ref-4). La última página muestra el error del modelo día por día.

<br>

<p align="center"><a href="https://prediccion-demanda-energetica-ml.vercel.app/"><strong>Ver la demo →</strong></a></p>

> Si la demo no muestra datos al abrirla, espera unos segundos y recarga. La API puede tardar en arrancar.

<br>

<p align="center">
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python"></a>
  <a href="https://pandas.pydata.org/"><img src="https://img.shields.io/badge/pandas-150458?style=for-the-badge&logo=pandas&logoColor=white" alt="pandas"></a>
  <a href="https://numpy.org/"><img src="https://img.shields.io/badge/NumPy-013243?style=for-the-badge&logo=numpy&logoColor=white" alt="NumPy"></a>
  <a href="https://scikit-learn.org/"><img src="https://img.shields.io/badge/scikit--learn-F7931E?style=for-the-badge&logo=scikitlearn&logoColor=white" alt="scikit-learn"></a>
  <a href="https://mlflow.org/"><img src="https://img.shields.io/badge/MLflow-0194E2?style=for-the-badge&logo=mlflow&logoColor=white" alt="MLflow"></a>
  <a href="https://fastapi.tiangolo.com/"><img src="https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI"></a>
  <a href="https://docs.pydantic.dev/"><img src="https://img.shields.io/badge/Pydantic-E92063?style=for-the-badge&logo=pydantic&logoColor=white" alt="Pydantic"></a>
  <a href="https://www.sqlalchemy.org/"><img src="https://img.shields.io/badge/SQLAlchemy-D71F00?style=for-the-badge&logo=sqlalchemy&logoColor=white" alt="SQLAlchemy"></a>
  <a href="https://www.postgresql.org/"><img src="https://img.shields.io/badge/PostgreSQL-4169E1?style=for-the-badge&logo=postgresql&logoColor=white" alt="PostgreSQL"></a>
  <a href="https://react.dev/"><img src="https://img.shields.io/badge/React-20232A?style=for-the-badge&logo=react&logoColor=61DAFB" alt="React"></a>
  <a href="https://www.typescriptlang.org/"><img src="https://img.shields.io/badge/TypeScript-3178C6?style=for-the-badge&logo=typescript&logoColor=white" alt="TypeScript"></a>
  <a href="https://vite.dev/"><img src="https://img.shields.io/badge/Vite-646CFF?style=for-the-badge&logo=vite&logoColor=white" alt="Vite"></a>
  <a href="https://www.docker.com/"><img src="https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white" alt="Docker"></a>
  <a href="https://nginx.org/"><img src="https://img.shields.io/badge/Nginx-009639?style=for-the-badge&logo=nginx&logoColor=white" alt="Nginx"></a>
  <a href="https://docs.pytest.org/"><img src="https://img.shields.io/badge/pytest-0A9EDC?style=for-the-badge&logo=pytest&logoColor=white" alt="pytest"></a>
  <a href="https://docs.astral.sh/ruff/"><img src="https://img.shields.io/badge/Ruff-D7FF64?style=for-the-badge&logo=ruff&logoColor=black" alt="Ruff"></a>
</p>

## Qué se puede hacer

- Pedir el pronóstico de cualquier fecha entre el 2 de enero de 2000 y el 31 de diciembre de 2023. El modelo solo usa los días anteriores a esa fecha.
- Ver el pronóstico junto a la demanda real de los 60 días previos.
- Revisar los pronósticos guardados con su demanda real, su error y el periodo al que pertenece la fecha (entrenamiento, validación o prueba).
- Comparar las versiones 1.1.0 y 1.2.0 del modelo en las mismas fechas.
- Ver las cinco páginas del informe de Power BI y descargarlo en PDF o `.pbix`.
- Consultar la demanda histórica y los pronósticos desde la API. La documentación está en `/docs`.
- Cambiar el idioma entre español e inglés.

En 2022 y 2023 el modelo se equivocó en promedio 2,78 GWh por día, con una demanda media de unos 215 GWh. Eso es un error de 1,30 %. La versión anterior tenía 5,32 %. Ver [Resultados](#resultados).

## Cómo funciona

```text
Archivos de XM (data/raw)
  -> ingesta y validación
  -> variables de cada fecha
  -> entrenamiento (MLflow)
  -> modelo activo en PostgreSQL
  -> API (FastAPI)
  -> aplicación web (React)
```

1. Los archivos anuales de XM se unen en una tabla con la demanda de cada día.
2. Para cada fecha se calculan variables con los días anteriores: la demanda de días atrás, promedios móviles y el calendario.
3. El modelo estima la razón entre la demanda de la fecha y la del mismo día de la semana anterior. El pronóstico es esa razón por la demanda real de hace siete días.
4. El modelo se guarda en MLflow y se marca como activo en la base de datos.
5. La API carga el modelo activo, pronostica la fecha pedida y guarda el resultado.
6. La web lee los pronósticos guardados. El informe de Power BI usa sus propios datos, exportados a CSV.

| Dato | Origen | Tipo |
|---|---|---|
| Demanda diaria del SIN | Archivos de XM | Real |
| Precio de bolsa, embalses y aportes hídricos | API de XM, solo en Power BI | Real |
| Índice ONI | NOAA, solo en Power BI | Real |
| Fase de El Niño o La Niña | Índice ONI (umbrales de +0,5 y −0,5) | Calculado |
| Festivos de Colombia | Ley 51 de 1983 | Calculado |
| Demanda de días anteriores, promedios móviles y calendario | Demanda histórica | Calculado |
| Demanda del día siguiente | Modelo activo | Predicho |

## Resultados

Los datos se separaron por años:

| Periodo | Años | Uso |
|---|---|---|
| Entrenamiento | 2000–2019 | Ajustar los modelos |
| Validación | 2020–2021 | Elegir modelos, variables y configuraciones |
| Prueba | 2022–2023 | Medir el resultado final una sola vez |

Los modelos se comparan con dos baselines. Un baseline es una regla fija, sin entrenamiento, como repetir la demanda de ayer. Un modelo útil tiene que equivocarse menos que esa regla.

Resultados en prueba (730 días, 2022–2023):

| Método | WAPE | MAE (GWh/día) | RMSE (GWh/día) |
|---|---:|---:|---:|
| Baseline: demanda del día anterior | 4,44 % | 9,53 | 13,18 |
| Baseline: demanda del mismo día de la semana anterior | 2,57 % | 5,51 | 8,60 |
| Modelo 1.0.0 | 5,93 % | 12,73 | 14,54 |
| Modelo 1.1.0 | 5,32 % | 11,42 | 13,71 |
| **Modelo 1.2.0 (entrenado con 2000–2019)** | **1,30 %** | **2,78** | 4,02 |
| Modelo 1.2.0 (reentrenado con 2000–2021, en uso) | 1,31 % | 2,82 | **3,99** |

La métrica principal es el WAPE: la suma de los errores absolutos dividida entre la suma de la demanda real, en porcentaje. Se usó porque permite comparar años con niveles de demanda distintos. El MAE (error absoluto medio) y el RMSE (que pesa más los errores grandes) están en GWh.

Por año y tipo de día:

| Método | 2022 | 2023 | 36 festivos | Días no festivos | Sesgo |
|---|---:|---:|---:|---:|---:|
| Mismo día de la semana anterior | 2,38 % | 2,75 % | 9,84 % | 2,23 % | −0,05 % |
| Modelo 1.1.0 | 3,55 % | 7,01 % | 4,04 % | 5,38 % | −5,05 % |
| Modelo 1.2.0 (2000–2019) | 1,26 % | 1,34 % | 4,81 % | 1,13 % | −0,09 % |

El sesgo es el error con signo. Si es negativo, el método predice menos demanda de la real.

### Interpretación de los resultados

Los modelos 1.0.0 y 1.1.0 tuvieron un WAPE de 2,73 % y 2,06 % en validación, pero mucho más alto en prueba. Un modelo de árboles de decisión no puede predecir valores mayores a los que vio al entrenar. La demanda más alta entre 2000 y 2019 fue de 217,0 GWh, y en 2023 hubo 241 días por encima de ese valor. El pronóstico más alto del modelo 1.1.0 para 2023 fue de 214,5 GWh, así que casi siempre se quedó corto. Su error mensual pasó de 2,6 % en enero a 10,6 % en septiembre. En validación no se notaba porque en 2020 y 2021 la demanda casi no pasó ese máximo, en parte por la pandemia.

El modelo 1.2.0 no predice la demanda sino su cambio frente a la semana anterior. El nivel sale de la demanda real de hace siete días, así que el pronóstico puede pasar el máximo de entrenamiento. En 2023 lo pasó en 244 días, y el error mensual quedó entre 0,7 % y 1,7 %.

Donde más falla es en los festivos. Los datos no marcan qué días son festivos, y si hubo uno siete días antes, el modelo arrastra ese efecto.

Con solo el historial de demanda, el modelo 1.2.0 tiene la mitad del error del mejor baseline y la cuarta parte del de la versión anterior. Casi no tiene sesgo y su error es parecido en 2022 y 2023.

## Informe de Power BI

El informe cubre el sistema eléctrico colombiano de 2000 a 2023: demanda, precio de bolsa, embalses, aportes hídricos, El Niño y La Niña, festivos y los pronósticos del modelo. Está en [PDF](docs/powerbi/reporte_demanda_energetica.pdf) y en [formato de Power BI Desktop](docs/powerbi/reporte_demanda_energetica.pbix), y la web muestra sus cinco páginas.

| Página | Pregunta | Visuales principales |
|---|---|---|
| Precio vs demanda | ¿El precio de bolsa sigue a la demanda? | Demanda y precio por mes, demanda diaria contra precio por fase de El Niño, variación anual y correlación |
| Hidrología y precio | ¿Los embalses y los aportes explican el precio? | Embalses contra precio por mes, aportes frente a su promedio histórico por fase de El Niño, índice ONI |
| Estructura de la demanda | ¿Cuándo sube y cuándo baja la demanda? | Calendario de demanda por semana y día, perfil por día de la semana, festivos contra días normales, 2020 frente a 2019 durante la pandemia |
| Balance del sistema | ¿Cómo se cubre la demanda? | Generación, importaciones y exportaciones por año, importaciones netas por mes, días con más energía no atendida |
| Desempeño del modelo | ¿Qué tan cerca queda el pronóstico de la demanda real? | MAE, WAPE y sesgo, pronóstico contra demanda real por día, WAPE móvil de 30 días, filtro por versión del modelo |

Cada página se puede filtrar por años.

<p align="center"><img src="frontend/public/powerbi/pages/page-1.webp" width="900" alt="Página Precio vs demanda"></p>
<p align="center"><img src="frontend/public/powerbi/pages/page-2.webp" width="900" alt="Página Hidrología y precio"></p>
<p align="center"><img src="frontend/public/powerbi/pages/page-3.webp" width="900" alt="Página Estructura de la demanda"></p>
<p align="center"><img src="frontend/public/powerbi/pages/page-4.webp" width="900" alt="Página Balance del sistema"></p>
<p align="center"><img src="frontend/public/powerbi/pages/page-5-v1.2.0.webp" width="900" alt="Página Desempeño del modelo"></p>

Los datos están en un esquema en estrella de seis tablas:

| Tabla | Granularidad | Origen |
|---|---|---|
| `dim_date` | Día, con festivos de Colombia | Generada |
| `fact_demand_daily` | Día | Archivos de XM |
| `fact_market_daily` | Día | API de XM: precio de bolsa, volumen útil de embalses y aportes |
| `dim_enso_monthly` | Mes | Índice ONI de NOAA |
| `dim_model` | Versión del modelo | Tabla `models` de PostgreSQL |
| `fact_prediction` | Día y versión del modelo | Tabla `energy_predictions` de PostgreSQL |

Los cálculos son más de 30 medidas DAX, que están en [`docs/powerbi/dax_measures.dax`](docs/powerbi/dax_measures.dax). Los colores están en `docs/powerbi/theme.json`.

Las tablas se generan como CSV en `data/powerbi/` con:

```bash
python scripts/run_powerbi_export.py
```

La primera vez necesita internet para descargar los datos de XM y NOAA. Después los toma de `data/powerbi/cache/`. Sin base de datos, las tablas de pronósticos quedan vacías y el resto del informe funciona. Los pasos para armar el informe están en [`docs/powerbi/README.md`](docs/powerbi/README.md).

## Inicio rápido

Requisitos: Docker con Docker Compose y una base de datos PostgreSQL (local o en un servicio como Supabase).

1. Crea las tablas en la base de datos:

   ```sql
   CREATE TABLE models (
       id UUID PRIMARY KEY,
       name TEXT NOT NULL,
       version TEXT NOT NULL,
       horizon INTEGER NOT NULL,
       is_active BOOLEAN NOT NULL DEFAULT false,
       created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
       CONSTRAINT uq_models_name_version UNIQUE (name, version)
   );

   CREATE TABLE energy_predictions (
       id UUID PRIMARY KEY,
       target_date DATE NOT NULL,
       predicted_demand_kwh DOUBLE PRECISION NOT NULL,
       actual_demand_kwh DOUBLE PRECISION NULL,
       model_id UUID NOT NULL REFERENCES models(id),
       created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
       CONSTRAINT uq_energy_predictions_target_model UNIQUE (target_date, model_id)
   );

   -- Solo un modelo puede estar activo a la vez
   CREATE UNIQUE INDEX uq_models_single_active ON models (is_active) WHERE is_active = true;
   ```

2. Crea un archivo `.env` en la raíz del proyecto:

   ```env
   DATABASE_URL=postgresql://usuario:clave@host:5432/base
   FRONTEND_ORIGIN=http://localhost:5173
   ```

3. Levanta los servicios:

   ```bash
   docker compose up --build -d
   ```

4. Registra el modelo 1.2.0 y actívalo:

   ```bash
   docker compose run --rm -v ./scripts:/app/scripts backend python scripts/register_serving_model.py --inactive --version 1.2.0 --execute
   docker compose run --rm -v ./scripts:/app/scripts backend python scripts/promote_serving_model.py 1.2.0 --execute
   ```

5. Abre `http://localhost:5173`. La API está en `http://localhost:8000` y su documentación en `http://localhost:8000/docs`.

Para detener los servicios: `docker compose down`.

### Sin Docker

Requisitos: Python 3.12 o 3.13 y Node.js 20.

```bash
python -m venv .venv
source .venv/bin/activate          # En Windows: .venv\Scripts\Activate.ps1
pip install -e ".[dev,ml]"

# API (desde la raíz del proyecto)
python -m uvicorn api.main:app --app-dir src --port 8000

# Aplicación web (en otra terminal)
cd frontend
npm install
npm run dev
```

Sin Docker se pueden consultar la demanda, el modelo activo y los pronósticos guardados. Para generar pronósticos nuevos hace falta Docker, porque los modelos están registrados en MLflow con la ruta del contenedor (`/app/mlruns`).

## Arquitectura

El entrenamiento se corre con scripts, aparte de la API. La API solo carga modelos ya entrenados, y la web solo se comunica con la API.

| Módulo | Responsabilidad |
|---|---|
| `src/ingestion` | Lectura de los archivos `.xlsx` y `.xls` de XM y unión en una tabla diaria |
| `src/validation` | Revisión de columnas, fechas duplicadas, fechas faltantes y valores nulos |
| `src/features` | Cálculo de las variables y lista de columnas de cada versión |
| `src/models` | Entrenamiento, modelo de razón semanal y versiones disponibles para la API |
| `src/evaluation` | Métricas (MAE, RMSE, sMAPE, WAPE) y comparación entre periodos |
| `src/tracking` | Registro de experimentos en MLflow |
| `src/database` | Tablas, conexión y consultas a PostgreSQL |
| `src/application` | Generar un pronóstico, consultar la demanda histórica y generar pronósticos por rango de fechas |
| `src/api` | Rutas y esquemas de FastAPI |
| `src/powerbi` | Descarga de datos de XM y NOAA, festivos y exportación de las tablas a CSV |
| `src/monitoring` | Logging |
| `frontend/src` | Aplicación React: componentes, cliente de la API, traducciones y formato |

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/health` | Estado del servicio |
| `GET` | `/api/v1/models/active` | Modelo activo: nombre, versión y horizonte |
| `GET` | `/api/v1/demand` | Demanda histórica, con filtros `start_date`, `end_date`, `page` y `page_size` |
| `GET` | `/api/v1/predictions` | Pronósticos guardados, con filtros de fecha, paginación y orden (`target_date` o `created_desc`) |
| `POST` | `/api/v1/predictions` | Genera y guarda el pronóstico de `target_date` con el modelo activo |

Ejemplo:

```http
POST /api/v1/predictions
Content-Type: application/json

{ "target_date": "2023-01-04" }
```

La respuesta trae `id`, `target_date`, `predicted_demand_kwh`, `actual_demand_kwh`, `model_id`, `model_name`, `model_version` y `horizon`. Si ya hay un pronóstico para esa fecha con ese modelo, la API responde `409`.

| Variable | Uso | Obligatoria |
|---|---|---|
| `DATABASE_URL` | Conexión a PostgreSQL | Sí |
| `FRONTEND_ORIGIN` | Origen permitido por CORS, por ejemplo `http://localhost:5173` | No |
| `ENVIRONMENT` | `development`, `testing` o `production` | No |
| `LOG_LEVEL` | `DEBUG`, `INFO`, `WARNING`, `ERROR` o `CRITICAL` | No |
| `MLFLOW_TRACKING_URI` | Carpeta de MLflow; en Docker es `file:///app/mlruns` | No |
| `VITE_API_BASE_URL` | URL de la API para la web | No |
| `VITE_POWERBI_EMBED_URL` | URL de un informe publicado en `powerbi.com` (solo `https`) | No |

## Reproducir el entrenamiento

Los archivos de XM ya están en `data/raw/`, así que no hay que descargar nada. Con el entorno instalado (`pip install -e ".[dev,ml]"`), desde la raíz del proyecto:

```bash
# Modelo 1.0.0
python scripts/run_ingestion.py
python scripts/run_features.py
python scripts/run_modeling.py
python scripts/run_evaluation.py
python scripts/run_mlflow_tracking.py

# Modelo 1.1.0
python scripts/run_phase11_feature_experiments.py
python scripts/run_phase11_validation_sensitivity.py
python scripts/run_phase11_model_comparison.py
python scripts/run_phase11_final_test_evaluation.py
python scripts/run_phase11_temporal_sensitivity_v1_v2.py
python scripts/run_phase10_v2.py

# Modelo 1.2.0
python scripts/run_phase12_ratio_target.py
```

Los resultados quedan en `data/interim/` y `data/processed/`. Los del modelo 1.2.0 están en `data/processed/phase12_ratio_target_results.json`.

El modelo 1.2.0 que usa la API se crea dentro del contenedor:

```bash
docker compose run --rm -v ./scripts:/app/scripts backend python scripts/create_serving_artifact_v1_2.py
```

Para generar pronósticos de un rango de fechas:

```bash
docker compose run --rm -v ./scripts:/app/scripts backend python scripts/backfill_predictions.py --start 2023-01-01 --end 2023-12-31 --model-version 1.2.0
```

## Pruebas

```bash
pytest                              # pruebas unitarias y de integración
ruff check .                        # estilo y análisis estático
npm --prefix frontend run build     # compilación del frontend
```

Las pruebas están en `tests/unit` y `tests/integration`. Hay una que revisa que el modelo no use datos del futuro: multiplica por cinco la demanda desde la fecha pronosticada en adelante y comprueba que las variables de esa fecha no cambien.

## Limitaciones

- Los datos terminan el 31 de diciembre de 2023, así que el sistema no pronostica fechas actuales.
- Los datos no marcan los festivos. En los 36 festivos del periodo de prueba, el WAPE es de 4,81 %.
- La fuente no tiene el registro del 31 de diciembre de 2015, y ese día no se rellena.
- Los modelos 1.1.0 y 1.2.0 están registrados con la ruta del contenedor, así que los pronósticos nuevos se generan en Docker.

## Roadmap

El proyecto se hizo por fases:

1. Definición del problema y de la arquitectura: una sola aplicación dividida en módulos, con el entrenamiento separado de la API.
2. Lectura de los 24 archivos de XM (`.xlsx` y `.xls`) y reporte de calidad. Ahí apareció que faltaba el 31 de diciembre de 2015.
3. Variables: demanda de 1, 7, 14 y 28 días antes, promedios y desviaciones móviles y calendario.
4. Primeros modelos: `RandomForestRegressor` y `HistGradientBoostingRegressor` contra un baseline semanal. El segundo fue el modelo 1.0.0.
5. Métricas por periodo (MAE, RMSE, sMAPE y WAPE) y registro de los experimentos en MLflow.
6. Tablas en PostgreSQL, API en FastAPI y la primera versión de la web.
7. Modelo 1.1.0: se agregó la demanda de los últimos tres días y el WAPE de validación bajó de 2,73 % a 2,06 %. La mejora se mantuvo al repetir la prueba sin los años de pandemia.
8. Docker para la API y la web, y publicación de la demo.
9. Modelo 1.2.0: al pronosticar todo 2023 se vio que el 1.1.0 nunca pasaba el máximo de entrenamiento. Se cambió a predecir la razón contra la semana anterior. Se probaron 24 configuraciones en validación y la elegida se evaluó una vez en prueba.
10. Informe de Power BI y versión final de la web, con las páginas del informe y la comparación entre versiones del modelo.

## Estructura del repositorio

| Ruta | Contenido |
|---|---|
| `src/` | Código del backend y de machine learning |
| `scripts/` | Ingesta, entrenamiento, experimentos, registro de modelos, pronósticos por rango y exportación a Power BI |
| `tests/` | Pruebas unitarias y de integración |
| `frontend/` | Aplicación React, su `Dockerfile` y la configuración de Nginx |
| `data/raw/` | Archivos anuales de demanda de XM, 2000–2023 |
| `data/interim/` | Serie diaria unida y reporte de calidad de la ingesta |
| `data/processed/` | Variables, pronósticos y resultados de cada experimento |
| `mlruns/` | Experimentos y modelos de MLflow |
| `docs/powerbi/` | Informe de Power BI (`.pbix` y PDF), medidas DAX y tema |
| `Dockerfile`, `docker-compose.yml` | Imagen de la API y arranque de la API y la web |
| `pyproject.toml` | Dependencias de Python y configuración de pytest y Ruff |

## Fuentes

1. <a id="ref-1"></a>XM. Informes de demanda de energía del Sistema Interconectado Nacional. https://www.xm.com.co/consumo/informes-demanda
2. <a id="ref-2"></a>XM. API pública de datos del mercado eléctrico colombiano. https://github.com/EquipoAnaliticaXM/API_XM
3. <a id="ref-3"></a>NOAA Climate Prediction Center. Oceanic Niño Index (ONI). https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/ensostuff/ONI_v5.php
4. <a id="ref-4"></a>Congreso de Colombia. Ley 51 de 1983, sobre el traslado de días festivos. https://www.funcionpublica.gov.co/eva/gestornormativo/norma.php?i=4954
