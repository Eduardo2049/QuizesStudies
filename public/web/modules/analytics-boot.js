/**
 * Stubs de fila do Vercel Web Analytics e Speed Insights.
 * Precisam existir antes dos loaders (/_vercel/insights/script.js e
 * /_vercel/speed-insights/script.js) serem executados, por isso são carregados
 * como <script src="..."> comum (bloqueante) antes deles no <head>.
 */
window.va = window.va || function () { (window.vaq = window.vaq || []).push(arguments); };
window.si = window.si || function () { (window.siq = window.siq || []).push(arguments); };
