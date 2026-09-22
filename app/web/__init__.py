"""
Interface Web local — terceiro modo de execução (recomendado).

Servidor HTTP da biblioteca padrão do Python (sem Flask, sem Node, sem nada
novo para instalar ou empacotar) servindo uma página única em HTML/CSS/JS
puro, acessível só por este computador (127.0.0.1) e protegida por uma chave
de acesso aleatória gerada a cada execução.

Reaproveita exatamente o mesmo núcleo da GUI e do terminal (app/core,
app/dashboard, app/notifications) — nenhuma regra de negócio é duplicada ou
alterada aqui, só exposta de outra forma.
"""
