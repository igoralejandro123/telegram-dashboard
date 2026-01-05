import requests
import time
import os
import psycopg2
from flask import Flask, request, redirect

app = Flask(__name__)
DATABASE_URL = os.getenv("DATABASE_URL")



def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

@app.route("/", methods=["GET", "POST"])
def dashboard():
    conn = get_db_connection()
    cur = conn.cursor()

    # =========================
    # SALVAR GASTOS
    # =========================
    if request.method == "POST":
        data = request.form["data"]
        tipo = request.form["tipo"]
        valor = request.form["valor"]
        descricao = request.form.get("descricao")

        cur.execute("""
            INSERT INTO gastos (data, tipo, valor, descricao)
            VALUES (%s, %s, %s, %s)
        """, (data, tipo, valor, descricao))
        conn.commit()
        return redirect("/")


    # =========================
    # MÉTRICAS DO BOT
    # =========================
    cur.execute("SELECT COUNT(DISTINCT user_id) FROM events")
    usuarios = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM events WHERE event = 'plan_click'")
    cliques = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM events WHERE event = 'purchase'")
    compras = cur.fetchone()[0]

    cur.execute("SELECT COALESCE(SUM(valor), 0) FROM events WHERE event = 'purchase'")
    faturamento_total = cur.fetchone()[0]

    cur.execute("""
        SELECT COALESCE(SUM(valor), 0)
        FROM events
        WHERE event = 'purchase'
        AND DATE(created_at) = CURRENT_DATE
    """)
    faturamento_hoje = cur.fetchone()[0]

    cur.execute("""
        SELECT COALESCE(SUM(valor), 0)
        FROM events
        WHERE event = 'purchase'
        AND DATE_TRUNC('month', created_at) = DATE_TRUNC('month', CURRENT_DATE)
    """)
    faturamento_mes = cur.fetchone()[0]

    # =========================
    # FINANCEIRO DIÁRIO
    # =========================
    cur.execute("""
        SELECT 
            d.data,
            COALESCE(f.faturamento, 0),
            COALESCE(g.facebook, 0),
            COALESCE(g.outros, 0)
        FROM (
            SELECT DISTINCT DATE(created_at) AS data FROM events
            UNION
            SELECT DISTINCT data FROM gastos
        ) d
        LEFT JOIN (
            SELECT DATE(created_at) AS data, SUM(valor) AS faturamento
            FROM events
            WHERE event = 'purchase'
            GROUP BY DATE(created_at)
        ) f ON f.data = d.data
        LEFT JOIN (
            SELECT data,
                SUM(CASE WHEN tipo = 'facebook' THEN valor ELSE 0 END) AS facebook,
                SUM(CASE WHEN tipo = 'outros' THEN valor ELSE 0 END) AS outros
            FROM gastos
            GROUP BY data
        ) g ON g.data = d.data
        ORDER BY d.data DESC
        LIMIT 30
    """)

    financeiro = cur.fetchall()

    cur.close()
    conn.close()

    linhas_financeiro = ""
    for d, fat, fb, outros in financeiro:
        gastos = fb + outros
        lucro = fat - gastos
        roi = (lucro / gastos * 100) if gastos > 0 else 0

        linhas_financeiro += f"""
        <tr>
            <td>{d}</td>
            <td>R$ {fat:.2f}</td>
            <td>R$ {fb:.2f}</td>
            <td>R$ {outros:.2f}</td>
            <td>R$ {gastos:.2f}</td>
            <td style="color:{'#22c55e' if lucro >= 0 else '#ef4444'}">
                R$ {lucro:.2f}
            </td>
            <td>{roi:.1f}%</td>
        </tr>
        """

    return f"""
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <title>Dashboard Bot Telegram</title>
        <style>
            body {{
                background:#0f0f12;
                color:#fff;
                font-family:Arial;
            }}
            .container {{
                max-width:1200px;
                margin:auto;
                padding:30px;
            }}
            h1 {{ margin-bottom:30px; }}

            .cards {{
                display:grid;
                grid-template-columns:repeat(auto-fit,minmax(220px,1fr));
                gap:20px;
            }}
            .card {{
                background:#1c1c22;
                padding:20px;
                border-radius:12px;
            }}
            .card h2 {{
                color:#aaa;
                font-size:14px;
            }}
            .card p {{
                font-size:28px;
                margin:10px 0 0;
                font-weight:bold;
            }}

            form {{
                background:#1c1c22;
                padding:20px;
                border-radius:12px;
                margin:40px 0;
            }}
            input, select, button {{
                padding:10px;
                margin-right:10px;
                border-radius:6px;
                border:none;
            }}
            button {{
                background:#22c55e;
                font-weight:bold;
            }}

            table {{
                width:100%;
                border-collapse:collapse;
            }}
            th, td {{
                padding:12px;
                border-bottom:1px solid #2a2a30;
                text-align:center;
            }}
            th {{ color:#aaa; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>📊 Dashboard — Bot Telegram VIP</h1>

            <div class="cards">
                <div class="card"><h2>Usuários</h2><p>{usuarios}</p></div>
                <div class="card"><h2>Cliques</h2><p>{cliques}</p></div>
                <div class="card"><h2>Compras</h2><p>{compras}</p></div>
                <div class="card"><h2>Faturamento hoje</h2><p>R$ {faturamento_hoje:.2f}</p></div>
                <div class="card"><h2>Faturamento mês</h2><p>R$ {faturamento_mes:.2f}</p></div>
                <div class="card"><h2>Faturamento total</h2><p>R$ {faturamento_total:.2f}</p></div>
            </div>

            <form method="post">
                <input type="date" name="data" required>
                <select name="tipo">
                    <option value="facebook">Facebook Ads</option>
                    <option value="outros">Outros gastos</option>
                </select>
                <input type="number" step="0.01" name="valor" placeholder="Valor" required>
                <input type="text" name="descricao" placeholder="Descrição">
                <button>Salvar gasto</button>
            </form>

            <table>
                <tr>
                    <th>Data</th>
                    <th>Faturamento</th>
                    <th>Facebook</th>
                    <th>Outros</th>
                    <th>Gastos</th>
                    <th>Lucro</th>
                    <th>ROI</th>
                </tr>
                {linhas_financeiro}
            </table>
        </div>
    </body>
    </html>
    """


# NÃO COLOQUE app.run()






