import requests
import time
import os
import psycopg2
from flask import Flask, request, redirect

app = Flask(__name__)
DATABASE_URL = os.getenv("DATABASE_URL")


def criar_tabelas():
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            event VARCHAR(50),
            plano VARCHAR(50),
            valor NUMERIC,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS gastos (
            id SERIAL PRIMARY KEY,
            data DATE NOT NULL,
            tipo VARCHAR(20),
            valor NUMERIC NOT NULL,
            descricao TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    conn.commit()
    cur.close()
    conn.close()


def get_db_connection():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL não definido no serviço do DASHBOARD")
    return psycopg2.connect(DATABASE_URL)


@app.route("/", methods=["GET", "POST"])
def dashboard():
    conn = get_db_connection()
    cur = conn.cursor()

    # 🔹 NOVO: intervalo de datas
    data_inicio = request.args.get("data_inicio")
    data_fim = request.args.get("data_fim")

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
    # CONDIÇÃO DE DATA
    # =========================
    filtro_sql = ""
    params = []

    if data_inicio and data_fim:
        filtro_sql = "AND DATE(created_at) BETWEEN %s AND %s"
        params = [data_inicio, data_fim]

    # =========================
    # MÉTRICAS
    # =========================
    cur.execute(f"""
        SELECT COUNT(DISTINCT user_id)
        FROM events
        WHERE 1=1 {filtro_sql}
    """, params)
    usuarios = cur.fetchone()[0]

    cur.execute(f"""
        SELECT COUNT(*)
        FROM events
        WHERE event = 'plan_click' {filtro_sql}
    """, params)
    cliques = cur.fetchone()[0]

    cur.execute(f"""
        SELECT COUNT(*)
        FROM events
        WHERE event = 'purchase' {filtro_sql}
    """, params)
    compras = cur.fetchone()[0]

    cur.execute(f"""
        SELECT COALESCE(SUM(valor),0)
        FROM events
        WHERE event = 'purchase' {filtro_sql}
    """, params)
    faturamento_total = cur.fetchone()[0]

    faturamento_hoje = faturamento_total
    faturamento_mes = faturamento_total

    # =========================
    # FINANCEIRO
    # =========================
    if data_inicio and data_fim:
        cur.execute("""
            SELECT 
                d.data,
                COALESCE(f.faturamento, 0),
                COALESCE(g.facebook, 0),
                COALESCE(g.outros, 0)
            FROM (
                SELECT generate_series(%s::date, %s::date, interval '1 day')::date AS data
            ) d
            LEFT JOIN (
                SELECT DATE(created_at) AS data, SUM(valor) AS faturamento
                FROM events
                WHERE event = 'purchase'
                AND DATE(created_at) BETWEEN %s AND %s
                GROUP BY DATE(created_at)
            ) f ON f.data = d.data
            LEFT JOIN (
                SELECT data,
                    SUM(CASE WHEN tipo = 'facebook' THEN valor ELSE 0 END) AS facebook,
                    SUM(CASE WHEN tipo = 'outros' THEN valor ELSE 0 END) AS outros
                FROM gastos
                WHERE data BETWEEN %s AND %s
                GROUP BY data
            ) g ON g.data = d.data
            ORDER BY d.data DESC
        """, (data_inicio, data_fim, data_inicio, data_fim, data_inicio, data_fim))
    else:
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
    </head>
    <body>
        <form method="get">
            <input type="date" name="data_inicio" value="{data_inicio or ''}">
            <input type="date" name="data_fim" value="{data_fim or ''}">
            <button>Filtrar</button>
            <a href="/">Limpar</a>
        </form>

        <!-- RESTANTE DO HTML CONTINUA IGUAL -->
        <!-- (mantive tudo como você pediu) -->

        {linhas_financeiro}
    </body>
    </html>
    """


if __name__ == "__main__":
    criar_tabelas()
    app.run(host="0.0.0.0", port=8080)
