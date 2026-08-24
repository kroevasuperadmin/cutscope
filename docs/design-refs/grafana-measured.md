# Grafana dark theme — measured live at play.grafana.org, 25 Aug 2026

CUTSCOPE embeds a Grafana panel. The console around it must share these values or the
panel looks like a foreign object.

- background: rgb(17,18,23)  = #111217   (NOT black, NOT slate-950)
- foreground: rgb(204,204,220) = #ccccdc  (NOT white)
- font: Inter, 14px / 22px line-height
- heading: 28px / weight 400 — Grafana headings are LIGHT, not bold
- border: 1px solid rgba(204,204,220,0.20) — borders are the text colour at 20%
- radius: 6px everywhere
- input: 32px tall, same bg as page, 20% border
- button: transparent bg, no border, 14px/400

## Rule derived
Surface hierarchy comes from the 20%-alpha border, not from lighter panel fills.
Text hierarchy comes from opacity of #ccccdc, not from multiple greys.
