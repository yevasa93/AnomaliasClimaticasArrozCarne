# Variables climáticas mensuales desde estaciones del IDEAM

Generado por `clima_ideam.ipynb`. Periodo de estudio: 2013-01 a 2026-10 (166 meses).
El notebook contiene la explicación detallada de cada paso e indicador.

## Fuentes
- Precipitación diaria: `PrecipitacionNacionalDiaria.zip` (IDEAM, bart.ideam.gov.co, vía https; el http no respondió).
- Temperatura diaria: `TemperaturaNacionalDiaria.zip` (IDEAM).
- Catálogo Nacional de Estaciones (CNE): datos.gov.co, conjunto `hp9r-jxuu`.
- Solo se usa información del IDEAM; no hay relleno con fuentes satelitales.

## Variables y etiquetas (verificadas con los datos)
- `PTPM_CON_INTER`: precipitación total diaria (lectura de las 07:00, asignada a la fecha de lectura).
- `TSSM_MX_D` / `TSSM_MN_D`: máximo / mínimo de las 3 lecturas diarias de termómetro seco (07, 13 y 19 h).
  Los masivos no incluyen TMX_CON / TMN_CON. La Tmax usada subestima la real y la Tmin la sobreestima;
  `dias_tmax_ge35` es una cota inferior y `dias_calor_p90` es robusto al sesgo (indicador principal de calor).
- `dias_calor_p90`: el 8,9 % de los días del periodo base supera el p90 (empates por resolución de 0,2 °C);
  la frecuencia crece de 6,6 % (1991-2002) a 13,5 % (2013-2020) por la tendencia de calentamiento.

## Criterios de selección
- Altitud máxima 1000 m s. n. m.; completitud mínima 70% por variable en el periodo de estudio.
- `dias_calor_p90`: al menos 10 años de Tmax entre 1991 y 2012;
  percentil sobre 1991-2020 por estación y mes calendario.
- Tecnologías excluidas: ninguna (las series `_CON` son convencionales).

### Estaciones que cumplen completitud según altitud máxima

| departamento | p90_1000m | p90_1500m | precip_1000m | precip_1500m | temp_1000m | temp_1500m |
|---|---|---|---|---|---|---|
| Antioquia | 5 | 12 | 61 | 83 | 6 | 13 |
| Caquetá | 4 | 4 | 15 | 15 | 4 | 4 |
| Casanare | 5 | 5 | 28 | 29 | 5 | 5 |
| Cesar | 4 | 4 | 54 | 55 | 4 | 4 |
| Córdoba | 12 | 12 | 54 | 54 | 13 | 13 |
| Huila | 3 | 7 | 40 | 68 | 3 | 9 |
| Meta | 6 | 6 | 49 | 52 | 6 | 6 |
| Norte de Santander | 4 | 6 | 29 | 39 | 4 | 6 |
| Tolima | 12 | 12 | 47 | 59 | 12 | 12 |

### Estaciones usadas por departamento (altitud <= 1000 m)

| departamento | estaciones | con_precip | con_temp | con_p90 | completitud_precip_media | completitud_temp_media |
|---|---|---|---|---|---|---|
| Antioquia | 61 | 61 | 6 | 5 | 94.2 | 72.0 |
| Caquetá | 15 | 15 | 4 | 4 | 86.1 | 71.7 |
| Casanare | 28 | 28 | 5 | 5 | 90.6 | 79.6 |
| Cesar | 54 | 54 | 4 | 4 | 92.1 | 58.7 |
| Córdoba | 54 | 54 | 13 | 12 | 91.7 | 85.0 |
| Huila | 40 | 40 | 3 | 3 | 92.4 | 72.1 |
| Meta | 49 | 49 | 6 | 6 | 93.1 | 73.1 |
| Norte de Santander | 29 | 29 | 4 | 4 | 94.2 | 64.8 |
| Tolima | 47 | 47 | 12 | 12 | 93.3 | 82.4 |

## Control de calidad diario
Precipitación < 0.0 o > 500.0 mm/día; Tmax < 5.0 o > 45.0 °C; Tmin > Tmax (ambas);
fechas repetidas. Un mes de una estación queda NaN con menos del 80% de días con dato.

| regla | total |
|---|---|
| precip_dias_repetidos | 16 |
| precip_descartados_rango | 0 |
| temp_dias_repetidos | 0 |
| tmax_descartados_rango | 1 |
| temp_descartados_tmin_gt_tmax | 0 |

## Indicadores
tmax_media, tmin_media, dias_calor_p90, dias_tmax_ge35, precip_total_mm, dias_lluvia (>= 1.0 mm),
dias_lluvia_fuerte (>= 20.0 mm), max_racha_seca. Los conteos se reescalan al largo del mes;
`max_racha_seca` y `precip_total_mm` no. Sin THI. No hay indicador de frío extremo ni de lluvia relativa (percentil).

## Agregación
- Departamento: promedio de estaciones válidas; tmax/tmin por anomalías + climatología fija del departamento.
- Producto: promedio ponderado renormalizado; NaN si el peso cubierto es menor al 50%.

### Pesos (fijos)
- Arroz: producción anual (miles de t), promedio 2013-2025, DANE-Fedearroz ENAM (Norte de Santander 2018-2025).
- Res: inventario bovino (millones de cabezas), promedio censos ICA 2018 y 2020-2025.

| producto | departamento | peso | participacion_% |
|---|---|---|---|
| arroz | Casanare | 881.6 | 35.9 |
| arroz | Meta | 387.4 | 15.8 |
| arroz | Tolima | 713.3 | 29.0 |
| arroz | Huila | 239.5 | 9.7 |
| arroz | Norte de Santander | 235.1 | 9.6 |
| res | Antioquia | 3.193 | 23.3 |
| res | Meta | 2.241 | 16.4 |
| res | Casanare | 2.2 | 16.1 |
| res | Córdoba | 2.31 | 16.9 |
| res | Caquetá | 2.154 | 15.7 |
| res | Cesar | 1.583 | 11.6 |

### Meses sin dato por departamento

| departamento | meses_nan_tmax | meses_nan_p90 | meses_nan_precip | min_est_temp | min_est_lluvia |
|---|---|---|---|---|---|
| Antioquia | 3 | 3 | 3 | 4 | 24 |
| Caquetá | 3 | 3 | 3 | 1 | 6 |
| Casanare | 3 | 3 | 3 | 2 | 10 |
| Cesar | 3 | 3 | 3 | 1 | 22 |
| Córdoba | 3 | 3 | 3 | 5 | 12 |
| Huila | 3 | 3 | 3 | 2 | 25 |
| Meta | 3 | 3 | 3 | 3 | 28 |
| Norte de Santander | 3 | 3 | 3 | 3 | 12 |
| Tolima | 3 | 3 | 3 | 8 | 26 |

## Cobertura de la tabla del modelo

| columna | meses_con_dato | meses_nan | pct_cobertura |
|---|---|---|---|
| arroz_tmax_media | 163 | 3 | 98.2 |
| arroz_dias_calor_p90 | 163 | 3 | 98.2 |
| arroz_dias_tmax_ge35 | 163 | 3 | 98.2 |
| arroz_precip_total_mm | 163 | 3 | 98.2 |
| arroz_dias_lluvia | 163 | 3 | 98.2 |
| arroz_dias_lluvia_fuerte | 163 | 3 | 98.2 |
| arroz_max_racha_seca | 163 | 3 | 98.2 |
| res_tmax_media | 163 | 3 | 98.2 |
| res_dias_calor_p90 | 163 | 3 | 98.2 |
| res_precip_total_mm | 163 | 3 | 98.2 |
| res_dias_lluvia | 163 | 3 | 98.2 |
| res_dias_lluvia_fuerte | 163 | 3 | 98.2 |
| res_max_racha_seca | 163 | 3 | 98.2 |

Los NaN restantes no se rellenan aquí; su tratamiento se decide en la etapa de modelado.
