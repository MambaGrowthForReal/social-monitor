# PROMPT MESTRE — AGENTE MONITOR DE MERCADO
## Mamba Growth | Nicho: Emagrecimento | Mercado: UK/US/DE

## INSTRUÇÕES DE EXECUÇÃO
Execute cada script na ordem abaixo. Após todas as coletas, gerar análise e fazer git commit + push para atualizar o dashboard.

## 1. YOUTUBE — 02:00
Run: python scripts/yt_search.py
Timeout: 20 minutos

## 2. FACEBOOK AD LIBRARY — 03:00
Run: python scripts/fb_search.py
Timeout: 20 minutos
Filtro de relevância: mantém apenas anúncios que contenham ao menos uma das palavras:
weight, loss, fat, pounds, slim, ozempic, mounjaro, belly, diet, lose, burn, melt,
calories, obesity, overweight, GLP, tirzepatide, semaglutide, bariatric, metaboli,
appetite, hunger, crave, slimming

## 3. GOOGLE TRENDS — 04:00
Run: python scripts/trends_search.py
Timeout: 20 minutos

## 4. TIKTOK (APIFY) — 05:00
Run: python scripts/apify_tiktok.py
Timeout: 20 minutos

## 5. PÓS-COLETA
Após todos os scripts:
- Gerar análise de tendências com base nos dados coletados
- Salvar em data/latest.json
- git add .
- git commit -m "auto: update $(date)"
- git push
