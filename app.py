from flask import Flask, render_template, request, redirect, url_for, Response, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime
from flask import jsonify
import io
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER

app = Flask(__name__)

# Configurar conexión a PostgreSQL
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql+psycopg://postgres:afusa2024@localhost:5432/afusa'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'afusa_secret_2024'

db = SQLAlchemy(app)

login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Iniciá sesión para continuar.'

# Modelo
class Jugador(db.Model):
    __tablename__ = 'jugador'

    id = db.Column(db.Integer, primary_key=True)
    codJugador = db.Column(db.Integer, nullable=False)
    nombreJugador = db.Column(db.String(100), nullable=False)
    apellidoJugador = db.Column(db.String(100), nullable=False)
    numeroDocumento = db.Column(db.String(20), unique=True, nullable=False)
    fechaNacimiento = db.Column(db.Date, nullable=False)
    adddate = db.Column(db.DateTime, default=db.func.now(), onupdate=db.func.now())
    alias = db.Column(db.String(50), nullable=True)
    activo = db.Column(db.Boolean, nullable=False, default=True, server_default='true')

    def __repr__(self):
        return f"<Jugador {self.nombreJugador} {self.apellidoJugador}>"
    
class TipoEgreso(db.Model):
    __tablename__ = 'tipoEgreso'
    idTipoEgreso = db.Column(db.Integer, primary_key=True, autoincrement=True)
    descripcion  = db.Column(db.String(100), nullable=False, unique=True)

class Egreso(db.Model):
    __tablename__ = 'egreso'
    id             = db.Column(db.Integer, primary_key=True, autoincrement=True)
    codTipoEgreso  = db.Column("codTipoEgreso", db.Integer,
                               db.ForeignKey('tipoEgreso.idTipoEgreso'), nullable=False)
    descripcion    = db.Column(db.String(200), nullable=True)
    importe        = db.Column(db.Numeric(10, 2), nullable=False)
    fechaEgreso    = db.Column("fechaEgreso", db.Date, nullable=False, default=datetime.now)

    tipo_egreso = db.relationship('TipoEgreso', backref=db.backref('egresos', lazy=True))

class TipoAporte(db.Model):
    __tablename__ = 'tipoAporte'
    idTipoAporte = db.Column(db.Integer, primary_key=True)
    descripcion  = db.Column(db.String(100), nullable=False)
    valor        = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    
class Aporte(db.Model):
    __tablename__ = 'aporte'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    codTipoAporte  = db.Column("codTipoAporte", db.Integer,
                               db.ForeignKey('tipoAporte.idTipoAporte'), nullable=False)
    descripcion    = db.Column(db.String(200), nullable=True)
    importe        = db.Column(db.Numeric(10, 2), nullable=False)
    idJugador      = db.Column("idJugador", db.Integer,
                               db.ForeignKey('jugador.id'), nullable=False)
    fechaAporte    = db.Column("fechaAporte", db.Date, nullable=False, default=datetime.now)

    jugador     = db.relationship('Jugador', backref=db.backref('aportes', lazy=True))
    tipo_aporte = db.relationship('TipoAporte', backref=db.backref('aportes', lazy=True))


class Usuario(UserMixin, db.Model):
    __tablename__ = 'usuario'
    id       = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(256), nullable=False)
    rol      = db.Column(db.String(20), nullable=False, default='operador')  # 'admin' | 'operador'
    activo   = db.Column(db.Boolean, default=True, nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(Usuario, int(user_id))

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.rol != 'admin':
            flash('Acceso restringido a administradores.', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated

def operador_blocked(f):
    """Bloquea acciones de escritura para el rol operador."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if current_user.rol == 'operador':
            flash('Tu rol no permite realizar esta acción.', 'error')
            return redirect(request.referrer or url_for('index'))
        return f(*args, **kwargs)
    return decorated


def calcular_sabados_transcurridos():
    """Sábados transcurridos desde el 1 de enero del año actual hasta hoy (inclusive)."""
    from datetime import date, timedelta
    hoy = date.today()
    inicio = date(hoy.year, 1, 1)
    dias_hasta_sabado = (5 - inicio.weekday()) % 7   # 5 = sábado
    primer_sabado = inicio + timedelta(days=dias_hasta_sabado)
    if primer_sabado > hoy:
        return 0
    return (hoy - primer_sabado).days // 7 + 1


# Ruta principal: lista y formulario
@app.route('/')
@login_required
def index():
    from sqlalchemy import extract
    jugadores = Jugador.query.order_by(Jugador.nombreJugador.asc()).all()

    # Calcular el siguiente código disponible
    ultimo_codigo = db.session.query(db.func.max(Jugador.codJugador)).scalar()
    siguiente_codigo = (ultimo_codigo or 0) + 1

    # Actividad del año: partidos disputados (Aporte Jornada) y última fecha
    anio_actual = datetime.now().year
    tipo_jornada = TipoAporte.query.filter_by(descripcion='Aporte Jornada').first()
    actividad = {}
    if tipo_jornada:
        stats = db.session.query(
            Aporte.idJugador,
            db.func.count(Aporte.id).label('partidos'),
            db.func.max(Aporte.fechaAporte).label('ultima_fecha')
        ).filter(
            Aporte.codTipoAporte == tipo_jornada.idTipoAporte,
            extract('year', Aporte.fechaAporte) == anio_actual
        ).group_by(Aporte.idJugador).all()
        actividad = {r.idJugador: {'partidos': r.partidos, 'ultima': r.ultima_fecha} for r in stats}

    total_sabados = calcular_sabados_transcurridos()
    return render_template('jugadores.html', jugadores=jugadores, siguiente_codigo=siguiente_codigo,
                           actividad=actividad, anio_actual=anio_actual, total_sabados=total_sabados)

# PDF listado de jugadores
@app.route('/jugadores/pdf')
@login_required
def jugadores_pdf():
    from sqlalchemy import extract
    from reportlab.lib.pagesizes import landscape, A4
    anio_actual = datetime.now().year
    jugadores = Jugador.query.order_by(Jugador.nombreJugador.asc(), Jugador.apellidoJugador.asc()).all()

    tipo_jornada = TipoAporte.query.filter_by(descripcion='Aporte Jornada').first()
    actividad = {}
    if tipo_jornada:
        stats = db.session.query(
            Aporte.idJugador,
            db.func.count(Aporte.id).label('partidos'),
            db.func.max(Aporte.fechaAporte).label('ultima_fecha')
        ).filter(
            Aporte.codTipoAporte == tipo_jornada.idTipoAporte,
            extract('year', Aporte.fechaAporte) == anio_actual
        ).group_by(Aporte.idJugador).all()
        actividad = {r.idJugador: {'partidos': r.partidos, 'ultima': r.ultima_fecha} for r in stats}

    styles = getSampleStyleSheet()
    afusa_style = ParagraphStyle('afusa', parent=styles['Normal'], fontSize=14,
                                 fontName='Helvetica-Bold', alignment=TA_CENTER,
                                 textColor=colors.HexColor('#2c5f8a'), spaceAfter=2)
    titulo_style = ParagraphStyle('tit', parent=styles['Heading2'], fontSize=11,
                                  alignment=TA_CENTER, spaceAfter=6)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4),
                            leftMargin=1.5*cm, rightMargin=1.5*cm,
                            topMargin=1.5*cm, bottomMargin=1.5*cm)
    elementos = []
    elementos.append(Paragraph(f"AFUSA 1997 - {anio_actual}", afusa_style))
    elementos.append(HRFlowable(width="100%", thickness=0.4, color=colors.HexColor('#2c5f8a'), spaceBefore=6, spaceAfter=8))
    elementos.append(Paragraph("Listado de Jugadores", titulo_style))
    elementos.append(Spacer(1, 0.3*cm))

    encabezado = ['Cód.', 'Nombre', 'Apellido', 'Documento', 'F. Nacimiento',
                  'Alias', 'F. Registro', f'Partidos {anio_actual}', 'Última participación']
    filas = [encabezado]
    for j in jugadores:
        act = actividad.get(j.id, {})
        filas.append([
            str(j.codJugador),
            j.nombreJugador,
            j.apellidoJugador,
            j.numeroDocumento or '',
            j.fechaNacimiento.strftime('%d/%m/%Y') if j.fechaNacimiento else '',
            j.alias or '',
            j.adddate.strftime('%d/%m/%Y') if j.adddate else '',
            str(act.get('partidos', '—')) if act.get('partidos') else '—',
            act['ultima'].strftime('%d/%m/%Y') if act.get('ultima') else '—',
        ])

    col_widths = [1.2*cm, 4.5*cm, 4.5*cm, 3*cm, 3*cm, 3*cm, 3*cm, 2.5*cm, 3.5*cm]
    tabla = Table(filas, colWidths=col_widths, repeatRows=1)
    tabla.setStyle(TableStyle([
        ('BACKGROUND',   (0,0), (-1,0), colors.HexColor('#2c5f8a')),
        ('TEXTCOLOR',    (0,0), (-1,0), colors.white),
        ('FONTNAME',     (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE',     (0,0), (-1,0), 8),
        ('FONTNAME',     (0,1), (-1,-1), 'Helvetica'),
        ('FONTSIZE',     (0,1), (-1,-1), 8),
        ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white, colors.HexColor('#f4f8fc')]),
        ('GRID',         (0,0), (-1,-1), 0.4, colors.HexColor('#c8d4e0')),
        ('ALIGN',        (0,0), (0,-1), 'CENTER'),
        ('ALIGN',        (7,0), (8,-1), 'CENTER'),
        ('VALIGN',       (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING',   (0,0), (-1,-1), 4),
        ('BOTTOMPADDING',(0,0), (-1,-1), 4),
    ]))
    elementos.append(tabla)

    doc.build(elementos)
    buf.seek(0)
    return Response(buf.read(), mimetype='application/pdf',
                    headers={'Content-Disposition': 'inline; filename="jugadores.pdf"'})

# PDF Registro de Asistencias (oficio)
@app.route('/jugadores/pdf/asistencias')
@login_required
def jugadores_pdf_asistencias():
    from reportlab.lib.pagesizes import portrait
    from reportlab.lib.units import inch
    from reportlab.platypus import KeepTogether

    anio_actual = datetime.now().year
    meses_n = ['enero','febrero','marzo','abril','mayo','junio',
               'julio','agosto','septiembre','octubre','noviembre','diciembre']
    dias_n  = ['lunes','martes','miércoles','jueves','viernes','sábado','domingo']
    hoy = datetime.now()
    fecha_larga = f"{dias_n[hoy.weekday()]} {hoy.day} de {meses_n[hoy.month-1]} de {hoy.year}".capitalize()

    from sqlalchemy import extract
    jugadores = Jugador.query.filter_by(activo=True)\
                    .order_by(Jugador.nombreJugador.asc(), Jugador.apellidoJugador.asc()).all()

    # Partidos disputados por jugador en el año actual
    tipo_jornada = TipoAporte.query.filter_by(descripcion='Aporte Jornada').first()
    partidos_map = {}
    if tipo_jornada:
        stats = db.session.query(
            Aporte.idJugador,
            db.func.count(Aporte.id).label('total')
        ).filter(
            Aporte.codTipoAporte == tipo_jornada.idTipoAporte,
            extract('year', Aporte.fechaAporte) == anio_actual
        ).group_by(Aporte.idJugador).all()
        partidos_map = {r.idJugador: r.total for r in stats}

    OFICIO = (8.5*inch, 13*inch)
    margen = 1.5*cm

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=portrait(OFICIO),
                            leftMargin=margen, rightMargin=margen,
                            topMargin=margen, bottomMargin=margen)

    styles = getSampleStyleSheet()
    afusa_style = ParagraphStyle('afusa', parent=styles['Normal'], fontSize=14,
                                 fontName='Helvetica-Bold', alignment=TA_CENTER,
                                 textColor=colors.HexColor('#2c5f8a'), spaceAfter=2)
    titulo_style = ParagraphStyle('tit', parent=styles['Heading2'], fontSize=11,
                                  alignment=TA_CENTER, spaceAfter=4)
    fecha_style  = ParagraphStyle('fec', parent=styles['Normal'], fontSize=10,
                                  alignment=TA_CENTER, spaceAfter=10)

    elementos = []
    elementos.append(Paragraph(f"AFUSA {anio_actual} — Registro de Asistencias", afusa_style))
    elementos.append(HRFlowable(width="100%", thickness=0.4, color=colors.HexColor('#2c5f8a'),
                                spaceBefore=6, spaceAfter=8))
    elementos.append(Paragraph(fecha_larga, fecha_style))

    total_sabados = calcular_sabados_transcurridos()

    # Ancho disponible: 8.5in - 2*margen
    ancho = 8.5*inch - 2*margen
    # Columnas: #, ID, Nombre Apellido, Asistencia %, Aporte Jornada, Cuota, Tarjetas, Nro
    col_w = [0.8*cm, 1.2*cm, 0, 1.8*cm, 3*cm, 2.2*cm, 2.2*cm, 1.8*cm]
    col_w[2] = ancho - sum(c for c in col_w if c)   # Nombre ocupa el resto

    fila_alto = 0.85*cm   # altura para escribir

    h_style = ParagraphStyle('h', fontSize=8, fontName='Helvetica-Bold', alignment=TA_CENTER)
    encabezado = [
        Paragraph('<b>#</b>',                        h_style),
        Paragraph('<b>ID</b>',                       h_style),
        Paragraph('<b>Nombre y Apellido</b>',        h_style),
        Paragraph('<b>Asistencia %</b>', h_style),
        Paragraph('<b>Aporte\nJornada</b>',          h_style),
        Paragraph('<b>Cuota</b>',                    h_style),
        Paragraph('<b>Tarjetas</b>',                 h_style),
        Paragraph('<b>Nro</b>',                      h_style),
    ]

    filas = [encabezado]
    extra_styles = []   # estilos de color por celda (fila, col)
    for idx, j in enumerate(jugadores, start=1):
        nombre = f"{j.nombreJugador} {j.apellidoJugador}"
        partidos = partidos_map.get(j.id, 0)
        if total_sabados > 0 and partidos:
            pct = round(partidos / total_sabados * 100, 1)
            color_pct = colors.HexColor('#1a7a2a') if pct >= 70 else colors.HexColor('#c0392b')
            pct_style = ParagraphStyle('p', fontSize=8, fontName='Helvetica-Bold',
                                       alignment=TA_CENTER, textColor=color_pct)
            pct_cell = Paragraph(f'{pct}% ({partidos})', pct_style)
        else:
            pct_cell = Paragraph('—', ParagraphStyle('p0', fontSize=8, alignment=TA_CENTER,
                                                     textColor=colors.HexColor('#aaaaaa')))
        filas.append([str(idx), str(j.codJugador), nombre, pct_cell, '', '', '', ''])

    n_datos = len(filas) - 1
    row_heights = [0.9*cm] + [fila_alto] * n_datos

    tabla = Table(filas, colWidths=col_w, rowHeights=row_heights, repeatRows=1)
    borde = colors.HexColor('#5a7a99')
    tabla.setStyle(TableStyle([
        # Encabezado
        ('BACKGROUND',    (0,0), (-1,0),  colors.HexColor('#5b9bd5')),
        ('TEXTCOLOR',     (0,0), (-1,0),  colors.white),
        ('FONTNAME',      (0,0), (-1,0),  'Helvetica-Bold'),
        ('FONTSIZE',      (0,0), (-1,0),  8),
        ('ALIGN',         (0,0), (-1,0),  'CENTER'),
        ('VALIGN',        (0,0), (-1,0),  'MIDDLE'),
        # Datos
        ('FONTNAME',      (0,1), (-1,-1), 'Helvetica'),
        ('FONTSIZE',      (0,1), (-1,-1), 8),
        ('ALIGN',         (0,1), (0,-1),  'CENTER'),   # ID centrado
        ('VALIGN',        (0,1), (-1,-1), 'MIDDLE'),
        ('ROWBACKGROUNDS',(0,1), (-1,-1), [colors.white, colors.HexColor('#f4f8fc')]),
        # Bordes
        ('GRID',          (0,0), (-1,-1), 0.5, borde),
        ('LINEBELOW',     (0,0), (-1,0),  1,   colors.HexColor('#5b9bd5')),
        # Padding
        ('TOPPADDING',    (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
        ('LEFTPADDING',   (0,0), (-1,-1), 4),
        ('RIGHTPADDING',  (0,0), (-1,-1), 4),
    ]))

    elementos.append(tabla)
    doc.build(elementos)
    buf.seek(0)
    return Response(buf.read(), mimetype='application/pdf',
                    headers={'Content-Disposition': f'inline; filename="asistencias_{anio_actual}.pdf"'})

# Crear jugador
@app.route('/add', methods=['POST'])
@login_required
@operador_blocked
def add_jugador():
     # Buscar el último código
    ultimo = db.session.query(db.func.max(Jugador.codJugador)).scalar()
    codJugador = (ultimo or 0) + 1  # si no hay jugadores arranca en 1

    nombre = request.form['nombreJugador']
    apellido = request.form['apellidoJugador']
    documento = request.form['numeroDocumento']
    fechaNacimiento = request.form['fechaNacimiento']  # AAAA-MM-DD
    alias = request.form.get('alias')  # opcional

    # Verificar documento duplicado
    if Jugador.query.filter_by(numeroDocumento=documento).first():
        from sqlalchemy import extract
        jugadores = Jugador.query.order_by(Jugador.nombreJugador.asc()).all()
        siguiente_codigo = codJugador
        anio_actual = datetime.now().year
        tipo_jornada = TipoAporte.query.filter_by(descripcion='Aporte Jornada').first()
        actividad = {}
        if tipo_jornada:
            stats = db.session.query(
                Aporte.idJugador,
                db.func.count(Aporte.id).label('partidos'),
                db.func.max(Aporte.fechaAporte).label('ultima_fecha')
            ).filter(
                Aporte.codTipoAporte == tipo_jornada.idTipoAporte,
                extract('year', Aporte.fechaAporte) == anio_actual
            ).group_by(Aporte.idJugador).all()
            actividad = {r.idJugador: {'partidos': r.partidos, 'ultima': r.ultima_fecha} for r in stats}
        return render_template('jugadores.html', jugadores=jugadores,
                               siguiente_codigo=siguiente_codigo,
                               actividad=actividad, anio_actual=anio_actual,
                               error=f"Ya existe un jugador con el documento «{documento}». Verificá el número ingresado.")

    nuevo = Jugador(
        codJugador=codJugador,
        nombreJugador=nombre,
        apellidoJugador=apellido,
        numeroDocumento=documento,
        fechaNacimiento=fechaNacimiento,
        alias=alias
    )
    db.session.add(nuevo)
    db.session.commit()
    return redirect(url_for('index'))

# Eliminar jugador
@app.route('/delete/<int:id>')
@login_required
@operador_blocked
def delete_jugador(id):
    jugador = Jugador.query.get_or_404(id)
    db.session.delete(jugador)
    db.session.commit()
    return redirect(url_for('index'))

# Editar jugador (cargar datos en formulario)
@app.route('/edit/<int:id>')
@login_required
def edit_jugador(id):
    from sqlalchemy import extract
    jugadores = Jugador.query.order_by(Jugador.nombreJugador.asc()).all()
    jugador = Jugador.query.get_or_404(id)
    anio_actual = datetime.now().year
    tipo_jornada = TipoAporte.query.filter_by(descripcion='Aporte Jornada').first()
    actividad = {}
    if tipo_jornada:
        stats = db.session.query(
            Aporte.idJugador,
            db.func.count(Aporte.id).label('partidos'),
            db.func.max(Aporte.fechaAporte).label('ultima_fecha')
        ).filter(
            Aporte.codTipoAporte == tipo_jornada.idTipoAporte,
            extract('year', Aporte.fechaAporte) == anio_actual
        ).group_by(Aporte.idJugador).all()
        actividad = {r.idJugador: {'partidos': r.partidos, 'ultima': r.ultima_fecha} for r in stats}
    total_sabados = calcular_sabados_transcurridos()
    return render_template('jugadores.html', jugadores=jugadores, jugador_edit=jugador,
                           actividad=actividad, anio_actual=anio_actual, total_sabados=total_sabados)

# Guardar edición
@app.route('/update/<int:id>', methods=['POST'])
@login_required
@operador_blocked
def update_jugador(id):
    jugador = Jugador.query.get_or_404(id)

    jugador.codJugador = request.form['codJugador']
    jugador.nombreJugador = request.form['nombreJugador']
    jugador.apellidoJugador = request.form['apellidoJugador']
    jugador.numeroDocumento = request.form['numeroDocumento']
    jugador.fechaNacimiento = request.form['fechaNacimiento']
    jugador.alias = request.form.get('alias')
    jugador.activo = request.form.get('activo', '1') == '1'

    db.session.commit()
    return redirect(url_for('index'))

@app.route('/jugadores/toggle/<int:id>', methods=['POST'])
@login_required
@operador_blocked
def toggle_jugador(id):
    jugador = Jugador.query.get_or_404(id)
    jugador.activo = not jugador.activo
    db.session.commit()
    return redirect(url_for('index'))

from datetime import datetime
import locale
# Para mostrar la fecha en español (si tu sistema soporta 'es_ES')
try:
    locale.setlocale(locale.LC_TIME, 'es_ES.UTF-8')
except:
    pass  # si no existe el locale en Windows/Linux, no se rompe

@app.route('/aportes', methods=['GET', 'POST'])
@login_required
def aportes():
    jugadores = Jugador.query.order_by(Jugador.nombreJugador.asc()).all()
    tipos = TipoAporte.query.order_by(TipoAporte.descripcion.asc()).all()
    
    if request.method == 'POST':
        codigo = (request.form.get('codigo_jugador') or '').strip()
        jugador_id = request.form.get('idJugador') or (
        Jugador.query.filter_by(codJugador=codigo).with_entities(Jugador.id).scalar() if codigo else None
        )       
        tipo_id = request.form.get('tipo_aporte')
        tipo = TipoAporte.query.get(int(tipo_id)) if tipo_id and str(tipo_id).isdigit() else None

        fecha = datetime.strptime(request.form.get('fechaAporte'), "%Y-%m-%d")
        importe = request.form.get('importe')

        # Si es Mensualidad y se indicó mes destino, guardar en descripcion
        mes_destino = request.form.get('mes_destino', '').strip()
        if tipo and tipo.descripcion == 'Mensualidad' and mes_destino:
            desc = f"mes:{mes_destino}"
        else:
            desc = tipo.descripcion if tipo else ''

        nuevo_aporte = Aporte(
            idJugador=jugador_id,
            codTipoAporte=(tipo.idTipoAporte if tipo else None),
            descripcion=desc,
            fechaAporte=fecha,
            importe=importe
            )
        db.session.add(nuevo_aporte)
        db.session.commit()

        fecha_str = fecha.strftime("%Y-%m-%d")
        return redirect(url_for('caja') + f'?tab=aportes&fecha_ap={fecha_str}')

    aportes = Aporte.query.all()
    aportes_data = []
    for a in aportes:
        fecha_formateada = a.fechaAporte.strftime("%A %d de %B de %Y").capitalize()
        aportes_data.append({
            "id": a.id,
            "jugador": f"{a.jugador.nombreJugador} {a.jugador.apellidoJugador}",
            "tipo": a.tipo_aporte.descripcion if a.tipo_aporte else '',
            "importe": a.importe,
            "fecha": fecha_formateada,
            "fechaRaw": a.fechaAporte.strftime("%Y-%m-%d"),
            "idJugador": a.idJugador,
            "codTipoAporte": a.codTipoAporte,
        })

    return render_template('aportes.html', jugadores=jugadores, tipos=tipos, datetime=datetime, aportes=aportes_data)

@app.route('/caja')
@login_required
def caja():
    jugadores   = Jugador.query.order_by(Jugador.nombreJugador.asc()).all()
    tipos_ap    = TipoAporte.query.order_by(TipoAporte.descripcion.asc()).all()
    tipos_eg    = TipoEgreso.query.order_by(TipoEgreso.descripcion.asc()).all()

    meses = ['enero','febrero','marzo','abril','mayo','junio',
             'julio','agosto','septiembre','octubre','noviembre','diciembre']
    dias  = ['lunes','martes','miércoles','jueves','viernes','sábado','domingo']

    def fmt_fecha(d):
        return f"{dias[d.weekday()]} {d.day} de {meses[d.month-1]} de {d.year}".capitalize()

    today = datetime.now().strftime("%Y-%m-%d")
    fecha_ap_str = request.args.get('fecha_ap', today)
    fecha_eg_str = request.args.get('fecha_eg', today)

    try:
        fecha_ap = datetime.strptime(fecha_ap_str, "%Y-%m-%d").date()
    except ValueError:
        fecha_ap = datetime.now().date()
        fecha_ap_str = fecha_ap.strftime("%Y-%m-%d")

    try:
        fecha_eg = datetime.strptime(fecha_eg_str, "%Y-%m-%d").date()
    except ValueError:
        fecha_eg = datetime.now().date()
        fecha_eg_str = fecha_eg.strftime("%Y-%m-%d")

    aportes_data = []
    for a in Aporte.query.filter(Aporte.fechaAporte == fecha_ap)\
               .join(Jugador, Aporte.idJugador == Jugador.id)\
               .order_by(Jugador.nombreJugador, Jugador.apellidoJugador,
                         Aporte.codTipoAporte).all():
        aportes_data.append({
            "id": a.id,
            "codJugador": a.jugador.codJugador,
            "jugador": f"{a.jugador.nombreJugador} {a.jugador.apellidoJugador}",
            "tipo": a.tipo_aporte.descripcion if a.tipo_aporte else '',
            "importe": a.importe,
            "fecha": a.fechaAporte.strftime("%d/%m/%Y"),
            "fechaRaw": a.fechaAporte.strftime("%Y-%m-%d"),
            "codTipoAporte": a.codTipoAporte,
            "idJugador": a.idJugador,
        })

    egresos_data = []
    for e in Egreso.query.filter(Egreso.fechaEgreso == fecha_eg).order_by(Egreso.id.desc()).all():
        egresos_data.append({
            "id": e.id,
            "tipo": e.tipo_egreso.descripcion if e.tipo_egreso else '',
            "codTipoEgreso": e.codTipoEgreso,
            "descripcion": e.descripcion,
            "importe": e.importe,
            "fecha": e.fechaEgreso.strftime("%d/%m/%Y"),
            "fechaRaw": e.fechaEgreso.strftime("%Y-%m-%d"),
        })

    # Última fecha de Aporte Jornada por jugador (año en curso)
    from sqlalchemy import extract
    _meses = ['enero','febrero','marzo','abril','mayo','junio',
              'julio','agosto','septiembre','octubre','noviembre','diciembre']
    _dias  = ['lunes','martes','miércoles','jueves','viernes','sábado','domingo']
    def _fecha_larga(d):
        return f"{_dias[d.weekday()]} {d.day} de {_meses[d.month-1]} de {d.year}".capitalize()

    tipo_jornada = TipoAporte.query.filter_by(descripcion='Aporte Jornada').first()
    ultima_jornada = {}
    if tipo_jornada:
        anio_caja = datetime.now().year
        # Obtener todos los aportes de jornada del año, ordenados desc por fecha
        aportes_jornada = db.session.query(
            Aporte.idJugador,
            Aporte.fechaAporte
        ).filter(
            Aporte.codTipoAporte == tipo_jornada.idTipoAporte,
            extract('year', Aporte.fechaAporte) == anio_caja
        ).order_by(Aporte.idJugador, Aporte.fechaAporte.desc()).all()

        # Agrupar por jugador: últimas 2 fechas únicas + conteo
        from collections import defaultdict
        jornadas_map = defaultdict(list)
        for row in aportes_jornada:
            jornadas_map[row.idJugador].append(row.fechaAporte)

        for jid, fechas in jornadas_map.items():
            # fechas ya ordenadas desc; tomar las 2 primeras únicas
            unicas = list(dict.fromkeys(fechas))[:2]
            ultima_jornada[jid] = {
                'fechas': [_fecha_larga(f) for f in unicas],
                'total': len(fechas)
            }

    return render_template('caja.html',
        jugadores=jugadores, tipos_ap=tipos_ap, tipos_eg=tipos_eg,
        aportes=aportes_data, egresos=egresos_data, datetime=datetime,
        fecha_ap=fecha_ap_str, fecha_eg=fecha_eg_str,
        ultima_jornada=ultima_jornada)


@app.route('/aportes/delete/<int:id>')
@login_required
@operador_blocked
def delete_aporte(id):
    aporte = Aporte.query.get_or_404(id)
    fecha_str = aporte.fechaAporte.strftime("%Y-%m-%d")
    db.session.delete(aporte)
    db.session.commit()
    return redirect(url_for('caja') + f'?tab=aportes&fecha_ap={fecha_str}')

@app.route('/aportes/update/<int:id>', methods=['POST'])
@login_required
@operador_blocked
def update_aporte(id):
    aporte = Aporte.query.get_or_404(id)
    tipo_id = request.form.get('tipo_aporte')
    tipo = TipoAporte.query.get(int(tipo_id)) if tipo_id and str(tipo_id).isdigit() else None
    aporte.fechaAporte = datetime.strptime(request.form.get('fechaAporte'), "%Y-%m-%d")
    aporte.codTipoAporte = tipo.idTipoAporte if tipo else aporte.codTipoAporte
    aporte.descripcion = tipo.descripcion if tipo else aporte.descripcion
    aporte.importe = request.form.get('importe')
    db.session.commit()
    fecha_str = aporte.fechaAporte.strftime("%Y-%m-%d")
    return redirect(url_for('caja') + f'?tab=aportes&fecha_ap={fecha_str}')

@app.route('/aportes/pdf')
@login_required
def aportes_pdf():
    fecha_str = request.args.get('fecha', '')
    try:
        fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date()
    except ValueError:
        return "Fecha inválida", 400

    # Fecha larga en español manualmente
    meses = ['enero','febrero','marzo','abril','mayo','junio',
             'julio','agosto','septiembre','octubre','noviembre','diciembre']
    dias = ['lunes','martes','miércoles','jueves','viernes','sábado','domingo']
    dia_semana = dias[fecha.weekday()]
    fecha_larga = f"{dia_semana} {fecha.day} de {meses[fecha.month-1]} de {fecha.year}".capitalize()

    aportes = Aporte.query.filter(Aporte.fechaAporte == fecha).order_by(Aporte.id).all()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)

    styles = getSampleStyleSheet()
    titulo_style = ParagraphStyle('titulo', parent=styles['Title'],
                                  fontSize=11, alignment=TA_CENTER, spaceAfter=12)
    msg_style = ParagraphStyle('msg', parent=styles['Normal'],
                               fontSize=11, alignment=TA_CENTER, spaceBefore=30)

    anio_actual = datetime.now().year
    afusa_style = ParagraphStyle('afusa', parent=styles['Normal'], fontSize=14,
                                 fontName='Helvetica-Bold', alignment=TA_CENTER,
                                 textColor=colors.HexColor('#2c5f8a'), spaceAfter=2)
    elementos = []
    elementos.append(Paragraph(f"AFUSA 1997 - {anio_actual}", afusa_style))
    elementos.append(HRFlowable(width="100%", thickness=0.4, color=colors.HexColor('#2c5f8a'), spaceBefore=6, spaceAfter=8))
    elementos.append(Paragraph(f"Resumen de la Jornada - {fecha_larga}", titulo_style))
    elementos.append(Spacer(1, 0.4*cm))

    if not aportes:
        elementos.append(Paragraph(f"No hay registros en la fecha seleccionada.", msg_style))
    else:
        subtitulo_style = ParagraphStyle('subtitulo', parent=styles['Heading2'],
                                         fontSize=11, spaceBefore=14, spaceAfter=5)
        col_widths = [8*cm, 3.5*cm, 3*cm]

        def make_tabla_tipo(filas, subtotal):
            data = [['Nombre y Apellido', 'Importe', 'Fecha']]
            for nombre, importe, fecha_str in filas:
                data.append([nombre, f"{importe:,.0f}".replace(',','.'), fecha_str])
            data.append(['SUBTOTAL', f"{subtotal:,.0f}".replace(',','.'), ''])
            t = Table(data, colWidths=col_widths, repeatRows=1)
            t.setStyle(TableStyle([
                ('BACKGROUND',    (0,0), (-1,0), colors.HexColor('#2c5f8a')),
                ('TEXTCOLOR',     (0,0), (-1,0), colors.white),
                ('FONTNAME',      (0,0), (-1,0), 'Helvetica-Bold'),
                ('FONTSIZE',      (0,0), (-1,0), 9),
                ('ALIGN',         (1,0), (1,-1), 'RIGHT'),
                ('ALIGN',         (2,0), (2,-1), 'CENTER'),
                ('FONTNAME',      (0,1), (-1,-2), 'Helvetica'),
                ('FONTSIZE',      (0,1), (-1,-2), 9),
                ('ROWBACKGROUNDS',(0,1), (-1,-2), [colors.white, colors.HexColor('#f0f4f8')]),
                ('FONTNAME',      (0,-1), (-1,-1), 'Helvetica-Bold'),
                ('BACKGROUND',    (0,-1), (-1,-1), colors.HexColor('#dce8f0')),
                ('GRID',          (0,0), (-1,-1), 0.5, colors.HexColor('#aaaaaa')),
                ('TOPPADDING',    (0,0), (-1,-1), 4),
                ('BOTTOMPADDING', (0,0), (-1,-1), 4),
            ]))
            return t

        # Agrupar por tipo, ordenar: Aporte Jornada primero, luego el resto alfabéticamente
        grupos = {}
        for a in aportes:
            tipo = a.tipo_aporte.descripcion if a.tipo_aporte else 'Sin tipo'
            grupos.setdefault(tipo, []).append(a)

        PRIMERO = 'Aporte Jornada'
        tipos_ordenados = sorted(grupos.keys(), key=lambda t: (0 if t == PRIMERO else 1, t))

        total_general = 0
        for tipo in tipos_ordenados:
            lista = sorted(grupos[tipo],
                           key=lambda a: (a.jugador.nombreJugador, a.jugador.apellidoJugador))
            subtotal = sum(int(a.importe) for a in lista)
            total_general += subtotal
            filas = [(f"{a.jugador.nombreJugador} {a.jugador.apellidoJugador}",
                      int(a.importe),
                      a.fechaAporte.strftime("%d/%m/%Y")) for a in lista]
            elementos.append(Paragraph(tipo, subtitulo_style))
            elementos.append(make_tabla_tipo(filas, subtotal))

        # Total general al pie
        elementos.append(Spacer(1, 0.5*cm))
        tot_data = [['TOTAL GENERAL', f"{total_general:,.0f}".replace(',','.')]]
        tot_tabla = Table(tot_data, colWidths=[8*cm, 3.5*cm])
        tot_tabla.setStyle(TableStyle([
            ('BACKGROUND',    (0,0), (-1,-1), colors.HexColor('#1e4a6e')),
            ('TEXTCOLOR',     (0,0), (-1,-1), colors.white),
            ('FONTNAME',      (0,0), (-1,-1), 'Helvetica-Bold'),
            ('FONTSIZE',      (0,0), (-1,-1), 11),
            ('ALIGN',         (1,0), (1,-1), 'RIGHT'),
            ('TOPPADDING',    (0,0), (-1,-1), 6),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
            ('GRID',          (0,0), (-1,-1), 0.5, colors.HexColor('#aaaaaa')),
        ]))
        elementos.append(tot_tabla)

    doc.build(elementos)
    buffer.seek(0)
    nombre_archivo = f"jornada_{fecha_str}.pdf"
    return Response(buffer, mimetype='application/pdf',
                    headers={'Content-Disposition': f'inline; filename="{nombre_archivo}"'})

@app.route('/egresos', methods=['GET', 'POST'])
@login_required
@operador_blocked
def egresos():
    tipos = TipoEgreso.query.order_by(TipoEgreso.descripcion.asc()).all()

    if request.method == 'POST':
        tipo_id  = request.form.get('tipo_egreso')
        importe  = request.form.get('importe')
        desc     = request.form.get('descripcion', '').strip()
        fecha    = datetime.strptime(request.form.get('fechaEgreso'), "%Y-%m-%d")
        tipo     = TipoEgreso.query.get(int(tipo_id)) if tipo_id and str(tipo_id).isdigit() else None

        nuevo = Egreso(
            codTipoEgreso=tipo.idTipoEgreso if tipo else None,
            descripcion=desc or (tipo.descripcion if tipo else ''),
            importe=importe,
            fechaEgreso=fecha,
        )
        db.session.add(nuevo)
        db.session.commit()
        fecha_str = fecha.strftime("%Y-%m-%d")
        return redirect(url_for('caja') + f'?tab=egresos&fecha_eg={fecha_str}')

    lista = Egreso.query.order_by(Egreso.fechaEgreso.desc(), Egreso.id.desc()).all()
    meses = ['enero','febrero','marzo','abril','mayo','junio',
             'julio','agosto','septiembre','octubre','noviembre','diciembre']
    dias  = ['lunes','martes','miércoles','jueves','viernes','sábado','domingo']
    egresos_data = []
    for e in lista:
        fd = e.fechaEgreso
        fecha_larga = f"{dias[fd.weekday()]} {fd.day} de {meses[fd.month-1]} de {fd.year}".capitalize()
        egresos_data.append({
            'id': e.id,
            'tipo': e.tipo_egreso.descripcion if e.tipo_egreso else '',
            'codTipoEgreso': e.codTipoEgreso,
            'descripcion': e.descripcion,
            'importe': e.importe,
            'fecha': fecha_larga,
            'fechaRaw': fd.strftime("%Y-%m-%d"),
        })

    return render_template('egresos.html', tipos=tipos, egresos=egresos_data, datetime=datetime)

@app.route('/egresos/tipo/add', methods=['POST'])
@login_required
@operador_blocked
def add_tipo_egreso():
    desc = request.form.get('descripcion', '').strip()
    if desc:
        existe = TipoEgreso.query.filter_by(descripcion=desc).first()
        if not existe:
            db.session.add(TipoEgreso(descripcion=desc))
            db.session.commit()
    return redirect(url_for('caja') + '?tab=egresos')

@app.route('/egresos/tipo/edit/<int:id>', methods=['POST'])
@login_required
@operador_blocked
def edit_tipo_egreso(id):
    tipo = TipoEgreso.query.get_or_404(id)
    desc = request.form.get('descripcion', '').strip()
    if desc:
        tipo.descripcion = desc
        db.session.commit()
    return redirect(url_for('caja') + '?tab=egresos')

@app.route('/egresos/tipo/delete/<int:id>')
@login_required
@operador_blocked
def delete_tipo_egreso(id):
    tipo = TipoEgreso.query.get_or_404(id)
    if tipo.egresos:
        return redirect(url_for('caja') + '?tab=egresos')
    db.session.delete(tipo)
    db.session.commit()
    return redirect(url_for('caja') + '?tab=egresos')

@app.route('/egresos/delete/<int:id>')
@login_required
@operador_blocked
def delete_egreso(id):
    egreso = Egreso.query.get_or_404(id)
    fecha_str = egreso.fechaEgreso.strftime("%Y-%m-%d")
    db.session.delete(egreso)
    db.session.commit()
    return redirect(url_for('caja') + f'?tab=egresos&fecha_eg={fecha_str}')

@app.route('/egresos/update/<int:id>', methods=['POST'])
@login_required
@operador_blocked
def update_egreso(id):
    egreso  = Egreso.query.get_or_404(id)
    tipo_id = request.form.get('tipo_egreso')
    tipo    = TipoEgreso.query.get(int(tipo_id)) if tipo_id and str(tipo_id).isdigit() else None
    egreso.fechaEgreso   = datetime.strptime(request.form.get('fechaEgreso'), "%Y-%m-%d")
    egreso.codTipoEgreso = tipo.idTipoEgreso if tipo else egreso.codTipoEgreso
    egreso.descripcion   = request.form.get('descripcion', '').strip() or (tipo.descripcion if tipo else '')
    egreso.importe       = request.form.get('importe')
    db.session.commit()
    fecha_str = egreso.fechaEgreso.strftime("%Y-%m-%d")
    return redirect(url_for('caja') + f'?tab=egresos&fecha_eg={fecha_str}')

@app.route('/egresos/pdf')
@login_required
def egresos_pdf():
    fecha_str = request.args.get('fecha', '')
    try:
        fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date()
    except ValueError:
        return "Fecha inválida", 400

    meses = ['enero','febrero','marzo','abril','mayo','junio',
             'julio','agosto','septiembre','octubre','noviembre','diciembre']
    dias  = ['lunes','martes','miércoles','jueves','viernes','sábado','domingo']
    fecha_larga = f"{dias[fecha.weekday()]} {fecha.day} de {meses[fecha.month-1]} de {fecha.year}".capitalize()

    lista = Egreso.query.filter(Egreso.fechaEgreso == fecha).order_by(Egreso.id).all()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    titulo_style = ParagraphStyle('titulo', parent=styles['Title'],
                                  fontSize=11, alignment=TA_CENTER, spaceAfter=12)
    msg_style    = ParagraphStyle('msg', parent=styles['Normal'],
                                  fontSize=11, alignment=TA_CENTER, spaceBefore=30)
    subtitulo_style = ParagraphStyle('subtitulo', parent=styles['Heading2'],
                                     fontSize=11, spaceAfter=6)
    anio_actual = datetime.now().year
    afusa_style = ParagraphStyle('afusa', parent=styles['Normal'], fontSize=14,
                                 fontName='Helvetica-Bold', alignment=TA_CENTER,
                                 textColor=colors.HexColor('#2c5f8a'), spaceAfter=2)
    elementos = []
    elementos.append(Paragraph(f"AFUSA 1997 - {anio_actual}", afusa_style))
    elementos.append(HRFlowable(width="100%", thickness=0.4, color=colors.HexColor('#2c5f8a'), spaceBefore=6, spaceAfter=8))
    elementos.append(Paragraph(f"Resumen de Egresos - {fecha_larga}", titulo_style))
    elementos.append(Spacer(1, 0.4*cm))

    if not lista:
        elementos.append(Paragraph("No hay registros en la fecha seleccionada.", msg_style))
    else:
        data = [['Tipo de Egreso', 'Descripción', 'Importe', 'Fecha']]
        total = 0
        for e in lista:
            total += int(e.importe)
            data.append([
                e.tipo_egreso.descripcion if e.tipo_egreso else '',
                e.descripcion or '',
                f"{int(e.importe):,.0f}".replace(',', '.'),
                e.fechaEgreso.strftime("%d/%m/%Y"),
            ])
        data.append(['', 'TOTAL', f"{total:,.0f}".replace(',', '.'), ''])

        col_widths = [5*cm, 6*cm, 3*cm, 3.5*cm]
        tabla = Table(data, colWidths=col_widths, repeatRows=1)
        tabla.setStyle(TableStyle([
            ('BACKGROUND',    (0,0), (-1,0), colors.HexColor('#8a2c2c')),
            ('TEXTCOLOR',     (0,0), (-1,0), colors.white),
            ('FONTNAME',      (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE',      (0,0), (-1,0), 10),
            ('ALIGN',         (2,0), (2,-1), 'RIGHT'),
            ('ALIGN',         (3,0), (3,-1), 'CENTER'),
            ('FONTNAME',      (0,1), (-1,-2), 'Helvetica'),
            ('FONTSIZE',      (0,1), (-1,-2), 9),
            ('ROWBACKGROUNDS',(0,1), (-1,-2), [colors.white, colors.HexColor('#f8f0f0')]),
            ('FONTNAME',      (0,-1), (-1,-1), 'Helvetica-Bold'),
            ('BACKGROUND',    (0,-1), (-1,-1), colors.HexColor('#f0dcdc')),
            ('GRID',          (0,0), (-1,-1), 0.5, colors.HexColor('#aaaaaa')),
            ('TOPPADDING',    (0,0), (-1,-1), 5),
            ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ]))
        elementos.append(tabla)

        # Resumen por tipo
        elementos.append(Spacer(1, 0.8*cm))
        elementos.append(Paragraph("Resumen por Tipo de Egreso", subtitulo_style))
        resumen, conteo = {}, {}
        for e in lista:
            tipo = e.tipo_egreso.descripcion if e.tipo_egreso else 'Sin tipo'
            resumen[tipo] = resumen.get(tipo, 0) + int(e.importe)
            conteo[tipo]  = conteo.get(tipo, 0) + 1

        res_data = [['Tipo de Egreso', 'Cantidad', 'Total']]
        for tipo, subtotal in sorted(resumen.items()):
            res_data.append([tipo, str(conteo[tipo]), f"{subtotal:,.0f}".replace(',', '.')])
        res_data.append(['TOTAL', str(len(lista)), f"{total:,.0f}".replace(',', '.')])

        tabla_res = Table(res_data, colWidths=[7*cm, 3*cm, 3.5*cm])
        tabla_res.setStyle(TableStyle([
            ('BACKGROUND',    (0,0), (-1,0), colors.HexColor('#8a2c2c')),
            ('TEXTCOLOR',     (0,0), (-1,0), colors.white),
            ('FONTNAME',      (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE',      (0,0), (-1,0), 10),
            ('ALIGN',         (1,0), (-1,-1), 'RIGHT'),
            ('FONTNAME',      (0,1), (-1,-2), 'Helvetica'),
            ('FONTSIZE',      (0,1), (-1,-2), 9),
            ('ROWBACKGROUNDS',(0,1), (-1,-2), [colors.white, colors.HexColor('#f8f0f0')]),
            ('FONTNAME',      (0,-1), (-1,-1), 'Helvetica-Bold'),
            ('BACKGROUND',    (0,-1), (-1,-1), colors.HexColor('#f0dcdc')),
            ('GRID',          (0,0), (-1,-1), 0.5, colors.HexColor('#aaaaaa')),
            ('TOPPADDING',    (0,0), (-1,-1), 5),
            ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ]))
        elementos.append(tabla_res)

    doc.build(elementos)
    buffer.seek(0)
    return Response(buffer, mimetype='application/pdf',
                    headers={'Content-Disposition': f'inline; filename="egresos_{fecha_str}.pdf"'})

@app.route('/caja/pdf/jornada')
@login_required
def caja_pdf_jornada():
    fecha_str = request.args.get('fecha', '')
    try:
        fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date()
    except ValueError:
        return "Fecha inválida", 400

    meses = ['enero','febrero','marzo','abril','mayo','junio',
             'julio','agosto','septiembre','octubre','noviembre','diciembre']
    dias  = ['lunes','martes','miércoles','jueves','viernes','sábado','domingo']
    fecha_larga = f"{dias[fecha.weekday()]} {fecha.day} de {meses[fecha.month-1]} de {fecha.year}".capitalize()

    lista_ap = Aporte.query.filter(Aporte.fechaAporte == fecha).order_by(Aporte.id).all()
    lista_eg = Egreso.query.filter(Egreso.fechaEgreso == fecha).order_by(Egreso.id).all()

    total_ap = sum(int(a.importe) for a in lista_ap)
    total_eg = sum(int(e.importe) for e in lista_eg)
    saldo    = total_ap - total_eg

    def fmt(n): return f"{n:,.0f}".replace(',', '.')

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    titulo_style    = ParagraphStyle('tit',  parent=styles['Title'],  fontSize=11, alignment=TA_CENTER, spaceAfter=4)
    subtit_style    = ParagraphStyle('sub',  parent=styles['Heading2'],fontSize=11, spaceBefore=14, spaceAfter=5)
    msg_style       = ParagraphStyle('msg',  parent=styles['Normal'], fontSize=10, spaceAfter=6)
    saldo_style     = ParagraphStyle('sal',  parent=styles['Normal'], fontSize=12, spaceBefore=10,
                                     fontName='Helvetica-Bold', alignment=TA_CENTER)

    COLOR_AP = colors.HexColor('#2c5f8a')
    COLOR_EG = colors.HexColor('#8a2c2c')
    COLOR_BG_AP = colors.HexColor('#f0f4f8')
    COLOR_BG_EG = colors.HexColor('#f8f0f0')
    COLOR_TOT_AP = colors.HexColor('#dce8f0')
    COLOR_TOT_EG = colors.HexColor('#f0dcdc')

    def make_tabla(data, col_widths, color_header, color_alt, color_total):
        t = Table(data, colWidths=col_widths, repeatRows=1)
        t.setStyle(TableStyle([
            ('BACKGROUND',    (0,0), (-1,0), color_header),
            ('TEXTCOLOR',     (0,0), (-1,0), colors.white),
            ('FONTNAME',      (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE',      (0,0), (-1,0), 9),
            ('ALIGN',         (2,0), (2,-1), 'RIGHT'),
            ('ALIGN',         (3,0), (3,-1), 'CENTER'),
            ('FONTNAME',      (0,1), (-1,-2), 'Helvetica'),
            ('FONTSIZE',      (0,1), (-1,-2), 9),
            ('ROWBACKGROUNDS',(0,1), (-1,-2), [colors.white, color_alt]),
            ('FONTNAME',      (0,-1), (-1,-1), 'Helvetica-Bold'),
            ('BACKGROUND',    (0,-1), (-1,-1), color_total),
            ('GRID',          (0,0), (-1,-1), 0.4, colors.HexColor('#aaaaaa')),
            ('TOPPADDING',    (0,0), (-1,-1), 4),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ]))
        return t

    def make_resumen(resumen, conteo, total, color_header, color_alt, color_total):
        data = [['Tipo', 'Cantidad', 'Total']]
        for tipo, subtotal in sorted(resumen.items()):
            data.append([tipo, str(conteo[tipo]), fmt(subtotal)])
        data.append(['TOTAL', str(sum(conteo.values())), fmt(total)])
        t = Table(data, colWidths=[7*cm, 2.5*cm, 3*cm])
        t.setStyle(TableStyle([
            ('BACKGROUND',    (0,0), (-1,0), color_header),
            ('TEXTCOLOR',     (0,0), (-1,0), colors.white),
            ('FONTNAME',      (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE',      (0,0), (-1,-1), 9),
            ('ALIGN',         (1,0), (-1,-1), 'RIGHT'),
            ('ROWBACKGROUNDS',(0,1), (-1,-2), [colors.white, color_alt]),
            ('FONTNAME',      (0,-1), (-1,-1), 'Helvetica-Bold'),
            ('BACKGROUND',    (0,-1), (-1,-1), color_total),
            ('GRID',          (0,0), (-1,-1), 0.4, colors.HexColor('#aaaaaa')),
            ('TOPPADDING',    (0,0), (-1,-1), 4),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ]))
        return t

    # Calcular resúmenes
    res_ap, cnt_ap = {}, {}
    for a in lista_ap:
        t = a.tipo_aporte.descripcion if a.tipo_aporte else 'Sin tipo'
        res_ap[t] = res_ap.get(t, 0) + int(a.importe)
        cnt_ap[t] = cnt_ap.get(t, 0) + 1

    res_eg, cnt_eg = {}, {}
    for e in lista_eg:
        t = e.tipo_egreso.descripcion if e.tipo_egreso else 'Sin tipo'
        res_eg[t] = res_eg.get(t, 0) + int(e.importe)
        cnt_eg[t] = cnt_eg.get(t, 0) + 1

    anio_actual = datetime.now().year
    afusa_style = ParagraphStyle('afusa', parent=styles['Normal'], fontSize=14,
                                 fontName='Helvetica-Bold', alignment=TA_CENTER,
                                 textColor=colors.HexColor('#2c5f8a'), spaceAfter=2)
    elementos = []
    elementos.append(Paragraph(f"AFUSA 1997 - {anio_actual}", afusa_style))
    elementos.append(HRFlowable(width="100%", thickness=0.4, color=colors.HexColor('#2c5f8a'), spaceBefore=6, spaceAfter=8))
    elementos.append(Paragraph("Resumen de la Jornada", titulo_style))
    elementos.append(Paragraph(fecha_larga, ParagraphStyle('fec', parent=styles['Normal'],
                                fontSize=11, alignment=TA_CENTER, spaceAfter=10)))
    elementos.append(Spacer(1, 0.3*cm))

    # --- RESUMEN APORTES ---
    elementos.append(Paragraph("Resumen de Aportes", subtit_style))
    if not lista_ap:
        elementos.append(Paragraph("Sin aportes en esta fecha.", msg_style))
    else:
        elementos.append(make_resumen(res_ap, cnt_ap, total_ap, COLOR_AP, COLOR_BG_AP, COLOR_TOT_AP))

    # --- RESUMEN EGRESOS ---
    elementos.append(Paragraph("Resumen de Egresos", subtit_style))
    if not lista_eg:
        elementos.append(Paragraph("Sin egresos en esta fecha.", msg_style))
    else:
        elementos.append(make_resumen(res_eg, cnt_eg, total_eg, COLOR_EG, COLOR_BG_EG, COLOR_TOT_EG))

    # Total general acumulado (todos los registros)
    total_ap_gral = int(db.session.query(db.func.coalesce(db.func.sum(Aporte.importe), 0)).scalar())
    total_eg_gral = int(db.session.query(db.func.coalesce(db.func.sum(Egreso.importe), 0)).scalar())
    saldo_gral    = total_ap_gral - total_eg_gral

    # --- BALANCE FINAL ---
    color_saldo_cel  = colors.HexColor('#1a7a1a') if saldo      >= 0 else colors.HexColor('#cc0000')
    color_saldo_gral = colors.HexColor('#1a7a1a') if saldo_gral >= 0 else colors.HexColor('#cc0000')

    def bal_style(color_ultima):
        return TableStyle([
            ('BACKGROUND',    (0,0), (-1,0),  colors.HexColor('#444444')),
            ('TEXTCOLOR',     (0,0), (-1,0),  colors.white),
            ('FONTNAME',      (0,0), (-1,0),  'Helvetica-Bold'),
            ('FONTSIZE',      (0,0), (-1,-1), 11),
            ('ALIGN',         (1,0), (1,-1),  'RIGHT'),
            ('FONTNAME',      (0,1), (-1,-2), 'Helvetica'),
            ('ROWBACKGROUNDS',(0,1), (-1,-2), [colors.white, colors.HexColor('#f5f5f5')]),
            ('FONTNAME',      (0,-1), (-1,-1), 'Helvetica-Bold'),
            ('BACKGROUND',    (0,-1), (-1,-1), color_ultima),
            ('TEXTCOLOR',     (0,-1), (-1,-1), colors.white),
            ('GRID',          (0,0),  (-1,-1), 0.4, colors.HexColor('#aaaaaa')),
            ('TOPPADDING',    (0,0),  (-1,-1), 6),
            ('BOTTOMPADDING', (0,0),  (-1,-1), 6),
        ])

    elementos.append(Spacer(1, 0.8*cm))
    elementos.append(Paragraph("Balance Final", subtit_style))

    # Tabla jornada
    bal_jornada = Table([
        ['Concepto', 'Importe'],
        ['Total Aportes',  fmt(total_ap)],
        ['Total Egresos',  fmt(total_eg)],
        ['Saldo de Jornada', fmt(abs(saldo))],
    ], colWidths=[8*cm, 4*cm])
    bal_jornada.setStyle(bal_style(color_saldo_cel))
    elementos.append(bal_jornada)

    # Separador
    elementos.append(Spacer(1, 0.3*cm))
    sep = Table([['', '']], colWidths=[8*cm, 4*cm])
    sep.setStyle(TableStyle([
        ('LINEABOVE',     (0,0), (-1,0), 2, colors.HexColor('#2c5f8a')),
        ('TOPPADDING',    (0,0), (-1,-1), 0),
        ('BOTTOMPADDING', (0,0), (-1,-1), 0),
    ]))
    elementos.append(sep)
    elementos.append(Spacer(1, 0.3*cm))

    # Tabla general
    bal_general = Table([
        ['Concepto', 'Importe'],
        ['Total Ingresos General', fmt(total_ap_gral)],
        ['Total Egresos General',  fmt(total_eg_gral)],
        ['Saldo en Caja',           fmt(abs(saldo_gral))],
    ], colWidths=[8*cm, 4*cm])
    bal_general.setStyle(bal_style(color_saldo_gral))
    elementos.append(bal_general)

    doc.build(elementos)
    buffer.seek(0)
    return Response(buffer, mimetype='application/pdf',
                    headers={'Content-Disposition': f'inline; filename="jornada_{fecha_str}.pdf"'})

@app.route('/informes')
@login_required
def informes():
    return render_template('informes.html')

@app.route('/api/mensualidades/<int:jugador_id>/<int:anio>')
@login_required
def api_mensualidades(jugador_id, anio):
    """Devuelve el estado de pago de mensualidades de un jugador en un año."""
    import re
    tipo_m = TipoAporte.query.filter_by(descripcion='Mensualidad').first()
    if not tipo_m:
        return jsonify({'meses': {}, 'siguiente': 1})

    aportes = Aporte.query.filter_by(idJugador=jugador_id, codTipoAporte=tipo_m.idTipoAporte).all()

    VALOR_MES = 20000
    meses = {}   # {mes_int: importe_acumulado}

    for a in aportes:
        # Intentar extraer mes destino del campo descripcion
        m = re.match(r'^mes:(\d{4})-(\d{2})$', a.descripcion or '')
        if m and int(m.group(1)) == anio:
            mes = int(m.group(2))
        elif not m:
            # Fallback: usar mes de fechaAporte solo si es del año solicitado
            if a.fechaAporte.year == anio:
                mes = a.fechaAporte.month
            else:
                continue
        else:
            continue
        meses[mes] = meses.get(mes, 0) + int(a.importe)

    resultado = {}
    for mes, total in meses.items():
        resultado[mes] = {'pagado': total, 'completo': total >= VALOR_MES}

    # Siguiente mes sin pago completo
    siguiente = 1
    for mes in range(1, 13):
        if resultado.get(mes, {}).get('completo', False):
            siguiente = mes + 1
        else:
            siguiente = mes
            break

    return jsonify({'meses': resultado, 'siguiente': min(siguiente, 12)})

def _pdf_informe(lista_ap, lista_eg, titulo, subtitulo):
    """Genera PDF de resumen aportes/egresos/balance para cualquier conjunto de registros."""
    def fmt(n): return f"{n:,.0f}".replace(',', '.')

    total_ap = sum(int(a.importe) for a in lista_ap)
    total_eg = sum(int(e.importe) for e in lista_eg)
    saldo    = total_ap - total_eg

    res_ap, cnt_ap = {}, {}
    for a in lista_ap:
        t = a.tipo_aporte.descripcion if a.tipo_aporte else 'Sin tipo'
        res_ap[t] = res_ap.get(t, 0) + int(a.importe)
        cnt_ap[t] = cnt_ap.get(t, 0) + 1

    res_eg, cnt_eg = {}, {}
    for e in lista_eg:
        t = e.tipo_egreso.descripcion if e.tipo_egreso else 'Sin tipo'
        res_eg[t] = res_eg.get(t, 0) + int(e.importe)
        cnt_eg[t] = cnt_eg.get(t, 0) + 1

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    titulo_style = ParagraphStyle('tit', parent=styles['Title'],  fontSize=11, alignment=TA_CENTER, spaceAfter=4)
    subtit_style = ParagraphStyle('sub', parent=styles['Heading2'], fontSize=11, spaceBefore=14, spaceAfter=5)
    msg_style    = ParagraphStyle('msg', parent=styles['Normal'],  fontSize=10, spaceAfter=6)

    COLOR_AP     = colors.HexColor('#2c5f8a')
    COLOR_EG     = colors.HexColor('#8a2c2c')
    COLOR_BG_AP  = colors.HexColor('#f0f4f8')
    COLOR_BG_EG  = colors.HexColor('#f8f0f0')
    COLOR_TOT_AP = colors.HexColor('#dce8f0')
    COLOR_TOT_EG = colors.HexColor('#f0dcdc')

    def make_resumen(resumen, conteo, total, color_header, color_alt, color_total):
        data = [['Tipo', 'Cantidad', 'Total']]
        for tipo, subtotal in sorted(resumen.items()):
            data.append([tipo, str(conteo[tipo]), fmt(subtotal)])
        data.append(['TOTAL', str(sum(conteo.values())), fmt(total)])
        t = Table(data, colWidths=[7*cm, 2.5*cm, 3*cm])
        t.setStyle(TableStyle([
            ('BACKGROUND',    (0,0), (-1,0), color_header),
            ('TEXTCOLOR',     (0,0), (-1,0), colors.white),
            ('FONTNAME',      (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE',      (0,0), (-1,-1), 9),
            ('ALIGN',         (1,0), (-1,-1), 'RIGHT'),
            ('ROWBACKGROUNDS',(0,1), (-1,-2), [colors.white, color_alt]),
            ('FONTNAME',      (0,-1), (-1,-1), 'Helvetica-Bold'),
            ('BACKGROUND',    (0,-1), (-1,-1), color_total),
            ('GRID',          (0,0), (-1,-1), 0.4, colors.HexColor('#aaaaaa')),
            ('TOPPADDING',    (0,0), (-1,-1), 4),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ]))
        return t

    anio_actual  = datetime.now().year
    afusa_style  = ParagraphStyle('afusa', parent=styles['Normal'], fontSize=14,
                                  fontName='Helvetica-Bold', alignment=TA_CENTER,
                                  textColor=colors.HexColor('#2c5f8a'), spaceAfter=2)
    subtit_inf   = ParagraphStyle('subtit_inf', parent=styles['Heading2'], fontSize=11,
                                  alignment=TA_CENTER, spaceAfter=4)
    sub2_style   = ParagraphStyle('sub2', parent=styles['Normal'],
                                  fontSize=10, alignment=TA_CENTER, spaceAfter=10)
    elementos = []
    elementos.append(Paragraph(f"AFUSA 1997 - {anio_actual}", afusa_style))
    elementos.append(HRFlowable(width="100%", thickness=0.4, color=colors.HexColor('#2c5f8a'), spaceBefore=6, spaceAfter=8))
    elementos.append(Paragraph(titulo, subtit_inf))
    elementos.append(Paragraph(subtitulo, sub2_style))
    elementos.append(Spacer(1, 0.3*cm))

    elementos.append(Paragraph("Resumen de Aportes", subtit_style))
    if not lista_ap:
        elementos.append(Paragraph("Sin aportes en el período.", msg_style))
    else:
        elementos.append(make_resumen(res_ap, cnt_ap, total_ap, COLOR_AP, COLOR_BG_AP, COLOR_TOT_AP))

    elementos.append(Paragraph("Resumen de Egresos", subtit_style))
    if not lista_eg:
        elementos.append(Paragraph("Sin egresos en el período.", msg_style))
    else:
        elementos.append(make_resumen(res_eg, cnt_eg, total_eg, COLOR_EG, COLOR_BG_EG, COLOR_TOT_EG))

    elementos.append(Spacer(1, 0.8*cm))
    elementos.append(Paragraph("Balance General", subtit_style))
    bal_data = [
        ['Concepto', 'Importe'],
        ['Total Aportes', fmt(total_ap)],
        ['Total Egresos', fmt(total_eg)],
        ['Saldo en Caja', fmt(abs(saldo))],
    ]
    color_saldo = colors.HexColor('#1a7a1a') if saldo >= 0 else colors.HexColor('#cc0000')
    bal_tabla = Table(bal_data, colWidths=[8*cm, 4*cm])
    bal_tabla.setStyle(TableStyle([
        ('BACKGROUND',    (0,0), (-1,0), colors.HexColor('#444444')),
        ('TEXTCOLOR',     (0,0), (-1,0), colors.white),
        ('FONTNAME',      (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE',      (0,0), (-1,-1), 11),
        ('ALIGN',         (1,0), (1,-1), 'RIGHT'),
        ('FONTNAME',      (0,1), (-1,-2), 'Helvetica'),
        ('ROWBACKGROUNDS',(0,1), (-1,-2), [colors.white, colors.HexColor('#f5f5f5')]),
        ('FONTNAME',      (0,-1), (-1,-1), 'Helvetica-Bold'),
        ('BACKGROUND',    (0,-1), (-1,-1), color_saldo),
        ('TEXTCOLOR',     (0,-1), (-1,-1), colors.white),
        ('GRID',          (0,0), (-1,-1), 0.4, colors.HexColor('#aaaaaa')),
        ('TOPPADDING',    (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
    ]))
    elementos.append(bal_tabla)

    doc.build(elementos)
    buffer.seek(0)
    return buffer

@app.route('/informes/pdf/periodo')
@login_required
def informes_pdf_periodo():
    desde_str = request.args.get('desde', '')
    hasta_str = request.args.get('hasta', '')
    try:
        desde = datetime.strptime(desde_str, "%Y-%m-%d").date()
        hasta = datetime.strptime(hasta_str, "%Y-%m-%d").date()
    except ValueError:
        return "Fechas inválidas", 400

    meses = ['enero','febrero','marzo','abril','mayo','junio',
             'julio','agosto','septiembre','octubre','noviembre','diciembre']
    subtitulo = (f"{desde.day} de {meses[desde.month-1]} de {desde.year}"
                 f" — {hasta.day} de {meses[hasta.month-1]} de {hasta.year}")

    lista_ap = Aporte.query.filter(Aporte.fechaAporte >= desde, Aporte.fechaAporte <= hasta).all()
    lista_eg = Egreso.query.filter(Egreso.fechaEgreso >= desde, Egreso.fechaEgreso <= hasta).all()

    buf = _pdf_informe(lista_ap, lista_eg, "Informe del Período", subtitulo)
    return Response(buf, mimetype='application/pdf',
                    headers={'Content-Disposition': f'inline; filename="informe_periodo_{desde_str}_{hasta_str}.pdf"'})

@app.route('/informes/pdf/periodo/detalle')
@login_required
def informes_pdf_periodo_detalle():
    desde_str = request.args.get('desde', '')
    hasta_str = request.args.get('hasta', '')
    try:
        desde = datetime.strptime(desde_str, "%Y-%m-%d").date()
        hasta = datetime.strptime(hasta_str, "%Y-%m-%d").date()
    except ValueError:
        return "Fechas inválidas", 400

    meses = ['enero','febrero','marzo','abril','mayo','junio',
             'julio','agosto','septiembre','octubre','noviembre','diciembre']
    subtitulo = (f"{desde.day} de {meses[desde.month-1]} de {desde.year}"
                 f" — {hasta.day} de {meses[hasta.month-1]} de {hasta.year}")

    lista_ap = (Aporte.query
                .filter(Aporte.fechaAporte >= desde, Aporte.fechaAporte <= hasta)
                .join(Jugador, Aporte.idJugador == Jugador.id)
                .order_by(Aporte.fechaAporte, Jugador.nombreJugador, Jugador.apellidoJugador)
                .all())
    lista_eg = (Egreso.query
                .filter(Egreso.fechaEgreso >= desde, Egreso.fechaEgreso <= hasta)
                .order_by(Egreso.fechaEgreso, Egreso.id)
                .all())

    def fmt(n): return f"{n:,.0f}".replace(',', '.')

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    titulo_style = ParagraphStyle('tit', parent=styles['Title'],  fontSize=11, alignment=TA_CENTER, spaceAfter=4)
    subtit_style = ParagraphStyle('sub', parent=styles['Normal'], fontSize=10, alignment=TA_CENTER, spaceAfter=10)
    sec_style    = ParagraphStyle('sec', parent=styles['Heading2'], fontSize=11, spaceBefore=14, spaceAfter=5)
    msg_style    = ParagraphStyle('msg', parent=styles['Normal'], fontSize=10, spaceAfter=6)

    anio_actual  = datetime.now().year
    afusa_style = ParagraphStyle('afusa', parent=styles['Normal'], fontSize=14,
                                 fontName='Helvetica-Bold', alignment=TA_CENTER,
                                 textColor=colors.HexColor('#2c5f8a'), spaceAfter=2)

    COLOR_AP  = colors.HexColor('#2c5f8a')
    COLOR_EG  = colors.HexColor('#8a2c2c')
    COLOR_ALT_AP = colors.HexColor('#f0f4f8')
    COLOR_ALT_EG = colors.HexColor('#f8f0f0')
    COLOR_TOT_AP = colors.HexColor('#dce8f0')
    COLOR_TOT_EG = colors.HexColor('#f0dcdc')

    def make_detalle(data, color_hdr, color_alt, color_tot):
        t = Table(data, colWidths=[2.5*cm, 5.5*cm, 3.5*cm, 2.5*cm], repeatRows=1)
        n = len(data)
        t.setStyle(TableStyle([
            ('BACKGROUND',    (0,0),  (-1,0),   color_hdr),
            ('TEXTCOLOR',     (0,0),  (-1,0),   colors.white),
            ('FONTNAME',      (0,0),  (-1,0),   'Helvetica-Bold'),
            ('FONTSIZE',      (0,0),  (-1,0),   9),
            ('ALIGN',         (3,0),  (3,-1),   'RIGHT'),
            ('ALIGN',         (0,0),  (0,-1),   'CENTER'),
            ('FONTNAME',      (0,1),  (-1,n-2), 'Helvetica'),
            ('FONTSIZE',      (0,1),  (-1,n-2), 8.5),
            ('ROWBACKGROUNDS',(0,1),  (-1,n-2), [colors.white, color_alt]),
            ('FONTNAME',      (0,-1), (-1,-1),  'Helvetica-Bold'),
            ('BACKGROUND',    (0,-1), (-1,-1),  color_tot),
            ('GRID',          (0,0),  (-1,-1),  0.4, colors.HexColor('#aaaaaa')),
            ('TOPPADDING',    (0,0),  (-1,-1),  4),
            ('BOTTOMPADDING', (0,0),  (-1,-1),  4),
        ]))
        return t

    elementos = [
        Paragraph(f"AFUSA 1997 - {anio_actual}", afusa_style),
        HRFlowable(width="100%", thickness=0.4, color=colors.HexColor('#2c5f8a'), spaceBefore=6, spaceAfter=8),
        Paragraph("Detalle del Período", titulo_style),
        Paragraph(subtitulo, subtit_style),
    ]

    # --- APORTES ---
    elementos.append(Paragraph("Aportes", sec_style))
    if not lista_ap:
        elementos.append(Paragraph("Sin aportes en el período.", msg_style))
    else:
        total_ap = sum(int(a.importe) for a in lista_ap)
        data_ap = [['Fecha', 'Jugador', 'Tipo', 'Importe']]
        for a in lista_ap:
            data_ap.append([
                a.fechaAporte.strftime("%d/%m/%Y"),
                f"{a.jugador.nombreJugador} {a.jugador.apellidoJugador}",
                a.tipo_aporte.descripcion if a.tipo_aporte else '',
                fmt(int(a.importe)),
            ])
        data_ap.append(['', 'TOTAL', '', fmt(total_ap)])
        elementos.append(make_detalle(data_ap, COLOR_AP, COLOR_ALT_AP, COLOR_TOT_AP))

    # --- EGRESOS ---
    elementos.append(Spacer(1, 0.6*cm))
    elementos.append(Paragraph("Egresos", sec_style))
    if not lista_eg:
        elementos.append(Paragraph("Sin egresos en el período.", msg_style))
    else:
        total_eg = sum(int(e.importe) for e in lista_eg)
        data_eg = [['Fecha', 'Descripción', 'Tipo', 'Importe']]
        for e in lista_eg:
            data_eg.append([
                e.fechaEgreso.strftime("%d/%m/%Y"),
                e.descripcion or '-',
                e.tipo_egreso.descripcion if e.tipo_egreso else '',
                fmt(int(e.importe)),
            ])
        data_eg.append(['', 'TOTAL', '', fmt(total_eg)])
        elementos.append(make_detalle(data_eg, COLOR_EG, COLOR_ALT_EG, COLOR_TOT_EG))

    doc.build(elementos)
    buffer.seek(0)
    return Response(buffer, mimetype='application/pdf',
                    headers={'Content-Disposition': f'inline; filename="detalle_periodo_{desde_str}_{hasta_str}.pdf"'})

@app.route('/informes/pdf/general')
@login_required
def informes_pdf_general():
    lista_ap = Aporte.query.all()
    lista_eg = Egreso.query.all()
    buf = _pdf_informe(lista_ap, lista_eg, "Resumen General", "Todos los registros")
    return Response(buf, mimetype='application/pdf',
                    headers={'Content-Disposition': 'inline; filename="informe_general.pdf"'})

@app.route('/informes/pdf/mensualidades')
@login_required
def informes_pdf_mensualidades():
    from sqlalchemy import extract
    anio = request.args.get('anio', datetime.now().year, type=int)

    tipo_m = TipoAporte.query.filter_by(descripcion='Mensualidad').first()
    if not tipo_m:
        return "Tipo 'Mensualidad' no encontrado", 400

    aportes = (Aporte.query
               .filter(Aporte.codTipoAporte == tipo_m.idTipoAporte,
                       extract('year', Aporte.fechaAporte) == anio)
               .all())

    # Construir dict: {jugador_id: {mes: total}}
    jugadores_all = (Jugador.query
                     .filter(Jugador.codJugador != 9999)
                     .order_by(Jugador.apellidoJugador.asc(), Jugador.nombreJugador.asc())
                     .all())
    jug_map = {j.id: j for j in jugadores_all}

    import re as _re
    VALOR_MES = 20000

    # Construir pagos por mes usando descripcion "mes:YYYY-MM" si existe, sino fechaAporte.month
    pagos_mes = {}  # {jugador_id: {mes_int: importe}}
    for a in aportes:
        jid = a.idJugador
        m = _re.match(r'^mes:(\d{4})-(\d{2})$', a.descripcion or '')
        if m:
            mes = int(m.group(2))
        else:
            mes = a.fechaAporte.month
        pagos_mes.setdefault(jid, {})
        pagos_mes[jid][mes] = pagos_mes[jid].get(mes, 0) + int(a.importe)

    # Total por jugador (para distribuir meses completos)
    totales_jug = {jid: sum(v.values()) for jid, v in pagos_mes.items()}

    # Sólo incluir jugadores con al menos 1 pago en el año
    jug_con_pago = [j for j in jugadores_all if j.id in totales_jug]

    def fmt(n): return f"{n:,.0f}".replace(',', '.') if n else '-'

    from reportlab.lib.pagesizes import landscape
    MESES_CORTOS = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic']

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4),
                            leftMargin=1.5*cm, rightMargin=1.5*cm,
                            topMargin=1.8*cm, bottomMargin=1.5*cm)
    styles = getSampleStyleSheet()
    titulo_style = ParagraphStyle('tit', parent=styles['Title'], fontSize=11,
                                  alignment=TA_CENTER, spaceAfter=4)
    subtit_mens  = ParagraphStyle('subtit_mens', parent=styles['Heading2'], fontSize=11,
                                  alignment=TA_CENTER, spaceAfter=4)
    sub_style    = ParagraphStyle('sub', parent=styles['Normal'], fontSize=10,
                                  alignment=TA_CENTER, spaceAfter=12)

    col_id     = 1.2*cm
    col_nombre = 4.8*cm
    col_mes    = 1.55*cm
    col_total  = 2.0*cm
    col_widths = [col_id, col_nombre] + [col_mes]*12 + [col_total]

    header = ['ID', 'Jugador'] + MESES_CORTOS + ['Total']
    data   = [header]

    totales_mes = {m: 0 for m in range(1, 13)}
    total_gral  = 0

    for j in jug_con_pago:
        mp = pagos_mes.get(j.id, {})
        fila = [str(j.codJugador), f"{j.apellidoJugador} {j.nombreJugador}"]
        total_jug = 0
        for mes in range(1, 13):
            v = mp.get(mes, 0)
            fila.append(fmt(v))
            totales_mes[mes] += v
            total_jug += v
        fila.append(fmt(total_jug))
        total_gral += total_jug
        data.append(fila)

    # Fila totales
    fila_tot = ['', 'TOTAL']
    for mes in range(1, 13):
        fila_tot.append(fmt(totales_mes[mes]))
    fila_tot.append(fmt(total_gral))
    data.append(fila_tot)

    COLOR_HDR  = colors.HexColor('#2c5f8a')
    COLOR_ALT  = colors.HexColor('#f0f4f8')
    COLOR_TOT  = colors.HexColor('#dce8f0')

    tabla = Table(data, colWidths=col_widths, repeatRows=1)
    n     = len(data)
    tabla.setStyle(TableStyle([
        # Header
        ('BACKGROUND',    (0,0),  (-1,0),  COLOR_HDR),
        ('TEXTCOLOR',     (0,0),  (-1,0),  colors.white),
        ('FONTNAME',      (0,0),  (-1,0),  'Helvetica-Bold'),
        ('FONTSIZE',      (0,0),  (-1,0),  8),
        ('ALIGN',         (0,0),  (0,-1),  'CENTER'),
        ('ALIGN',         (1,0),  (1,0),   'LEFT'),
        ('ALIGN',         (2,0),  (-1,0),  'CENTER'),
        # Datos
        ('FONTNAME',      (0,1),  (-1,n-2), 'Helvetica'),
        ('FONTSIZE',      (0,1),  (-1,n-2), 7.5),
        ('ALIGN',         (1,1),  (1,-1),  'LEFT'),
        ('ALIGN',         (2,1),  (-1,-1), 'RIGHT'),
        ('ROWBACKGROUNDS',(0,1),  (-1,n-2), [colors.white, COLOR_ALT]),
        # Fila total
        ('FONTNAME',      (0,-1), (-1,-1), 'Helvetica-Bold'),
        ('FONTSIZE',      (0,-1), (-1,-1), 8),
        ('BACKGROUND',    (0,-1), (-1,-1), COLOR_TOT),
        # Grid
        ('GRID',          (0,0),  (-1,-1), 0.3, colors.HexColor('#aaaaaa')),
        ('TOPPADDING',    (0,0),  (-1,-1), 3),
        ('BOTTOMPADDING', (0,0),  (-1,-1), 3),
    ]))

    anio_actual = datetime.now().year
    afusa_style = ParagraphStyle('afusa', parent=styles['Normal'], fontSize=14,
                                 fontName='Helvetica-Bold', alignment=TA_CENTER,
                                 textColor=colors.HexColor('#2c5f8a'), spaceAfter=2)
    elementos = [
        Paragraph(f"AFUSA 1997 - {anio_actual}", afusa_style),
        HRFlowable(width="100%", thickness=0.4, color=colors.HexColor('#2c5f8a'), spaceBefore=6, spaceAfter=8),
        Paragraph(f"Progreso de Mensualidades {anio}", subtit_mens),
        Paragraph(f"Jugadores con pagos registrados: {len(jug_con_pago)}", sub_style),
        tabla,
    ]
    doc.build(elementos)
    buffer.seek(0)
    return Response(buffer, mimetype='application/pdf',
                    headers={'Content-Disposition': f'inline; filename="mensualidades_{anio}.pdf"'})

@app.route('/informes/pdf/mensualidades/detalle')
@login_required
def informes_pdf_mensualidades_detalle():
    from sqlalchemy import extract
    import re as _re
    anio = request.args.get('anio', datetime.now().year, type=int)

    tipo_m = TipoAporte.query.filter_by(descripcion='Mensualidad').first()
    if not tipo_m:
        return "Tipo 'Mensualidad' no encontrado", 400

    cod_filtro = request.args.get('cod', '').strip()

    query = (Aporte.query
             .filter(Aporte.codTipoAporte == tipo_m.idTipoAporte)
             .join(Jugador, Aporte.idJugador == Jugador.id)
             .filter(Jugador.codJugador != 9999))

    if cod_filtro and cod_filtro.isdigit():
        query = query.filter(Jugador.codJugador == int(cod_filtro))

    aportes = query.order_by(Jugador.apellidoJugador, Jugador.nombreJugador, Aporte.fechaAporte).all()

    MESES = ['','Enero','Febrero','Marzo','Abril','Mayo','Junio',
             'Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre']

    def mes_num(a):
        """Devuelve (anio, mes) del destino del pago para ordenar."""
        m = _re.match(r'^mes:(\d{4})-(\d{2})$', a.descripcion or '')
        if m:
            return (int(m.group(1)), int(m.group(2)))
        return (a.fechaAporte.year, a.fechaAporte.month)

    def mes_destino(a):
        anio_m, mes_m = mes_num(a)
        return f"{MESES[mes_m]} {anio_m}"

    def fmt(n): return f"{n:,.0f}".replace(',', '.')

    from reportlab.lib.pagesizes import landscape
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4),
                            leftMargin=1.5*cm, rightMargin=1.5*cm,
                            topMargin=1.8*cm, bottomMargin=1.5*cm)
    styles = getSampleStyleSheet()
    titulo_style = ParagraphStyle('tit', parent=styles['Title'], fontSize=11,
                                  alignment=TA_CENTER, spaceAfter=4)
    sub_style    = ParagraphStyle('sub', parent=styles['Normal'], fontSize=10,
                                  alignment=TA_CENTER, spaceAfter=12)
    sec_style    = ParagraphStyle('sec', parent=styles['Heading3'], fontSize=10,
                                  spaceBefore=10, spaceAfter=3,
                                  textColor=colors.HexColor('#2c5f8a'))

    COLOR_HDR = colors.HexColor('#2c5f8a')
    COLOR_ALT = colors.HexColor('#f0f4f8')
    COLOR_TOT = colors.HexColor('#dce8f0')
    col_widths = [1.5*cm, 3.5*cm, 3.0*cm, 3.0*cm, 2.5*cm]

    # Agrupar por jugador
    jugadores_pagos = {}
    for a in aportes:
        key = a.idJugador
        jugadores_pagos.setdefault(key, {'jugador': a.jugador, 'pagos': []})
        jugadores_pagos[key]['pagos'].append(a)

    anio_actual = datetime.now().year
    afusa_style = ParagraphStyle('afusa', parent=styles['Normal'], fontSize=14,
                                 fontName='Helvetica-Bold', alignment=TA_CENTER,
                                 textColor=colors.HexColor('#2c5f8a'), spaceAfter=2)
    elementos = [
        Paragraph(f"AFUSA 1997 - {anio_actual}", afusa_style),
        HRFlowable(width="100%", thickness=0.4, color=colors.HexColor('#2c5f8a'), spaceBefore=6, spaceAfter=8),
        Paragraph(f"Detalle de Mensualidades — {'Jugador: ' + cod_filtro if cod_filtro else 'Todos los registros'}", titulo_style),
        Paragraph(f"Año de consulta: {anio}  |  Jugadores: {len(jugadores_pagos)}", sub_style),
    ]

    total_gral = 0
    for jid, info in sorted(jugadores_pagos.items(),
                             key=lambda x: (x[1]['jugador'].apellidoJugador,
                                            x[1]['jugador'].nombreJugador)):
        j = info['jugador']
        pagos = sorted(info['pagos'], key=mes_num)
        total_jug = sum(int(a.importe) for a in pagos)
        total_gral += total_jug

        elementos.append(Paragraph(
            f"{j.apellidoJugador} {j.nombreJugador}  —  Total: {fmt(total_jug)} Gs", sec_style))

        data = [['#', 'Jugador', 'Mes de Pago', 'Fecha de Registro', 'Importe']]
        for i, a in enumerate(pagos, 1):
            data.append([
                str(i),
                f"{j.nombreJugador} {j.apellidoJugador}",
                mes_destino(a),
                a.fechaAporte.strftime("%d/%m/%Y"),
                fmt(int(a.importe)),
            ])
        data.append(['', '', '', 'TOTAL', fmt(total_jug)])

        tabla = Table(data, colWidths=col_widths, repeatRows=1)
        n = len(data)
        tabla.setStyle(TableStyle([
            ('BACKGROUND',    (0,0),  (-1,0),  COLOR_HDR),
            ('TEXTCOLOR',     (0,0),  (-1,0),  colors.white),
            ('FONTNAME',      (0,0),  (-1,0),  'Helvetica-Bold'),
            ('FONTSIZE',      (0,0),  (-1,0),  8),
            ('ALIGN',         (0,0),  (0,-1),  'CENTER'),
            ('ALIGN',         (4,0),  (4,-1),  'RIGHT'),
            ('ALIGN',         (3,0),  (3,-1),  'CENTER'),
            ('FONTNAME',      (0,1),  (-1,n-2), 'Helvetica'),
            ('FONTSIZE',      (0,1),  (-1,n-2), 8),
            ('ROWBACKGROUNDS',(0,1),  (-1,n-2), [colors.white, COLOR_ALT]),
            ('FONTNAME',      (0,-1), (-1,-1), 'Helvetica-Bold'),
            ('BACKGROUND',    (0,-1), (-1,-1), COLOR_TOT),
            ('GRID',          (0,0),  (-1,-1), 0.3, colors.HexColor('#aaaaaa')),
            ('TOPPADDING',    (0,0),  (-1,-1), 3),
            ('BOTTOMPADDING', (0,0),  (-1,-1), 3),
        ]))
        elementos.append(tabla)

    # Total general
    elementos.append(Spacer(1, 0.5*cm))
    tot = Table([['TOTAL GENERAL', fmt(total_gral)]], colWidths=[10*cm, 3*cm])
    tot.setStyle(TableStyle([
        ('BACKGROUND',    (0,0), (-1,-1), colors.HexColor('#1e4a6e')),
        ('TEXTCOLOR',     (0,0), (-1,-1), colors.white),
        ('FONTNAME',      (0,0), (-1,-1), 'Helvetica-Bold'),
        ('FONTSIZE',      (0,0), (-1,-1), 11),
        ('ALIGN',         (1,0), (1,-1),  'RIGHT'),
        ('TOPPADDING',    (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('GRID',          (0,0), (-1,-1), 0.4, colors.HexColor('#aaaaaa')),
    ]))
    elementos.append(tot)

    doc.build(elementos)
    buffer.seek(0)
    return Response(buffer, mimetype='application/pdf',
                    headers={'Content-Disposition': f'inline; filename="mensualidades_detalle_{anio}.pdf"'})

@app.route('/about')
@login_required
def about():
    fecha_creacion = datetime.now().strftime("%d/%m/%Y")
    return render_template('about.html', fecha_creacion=fecha_creacion)

@app.route('/api/jugador/<codigo>')
@login_required
def api_jugador_por_codigo(codigo):
    # si codJugador es numérico en la DB, casteamos
    clave = int(codigo) if codigo.isdigit() else codigo
    j = Jugador.query.filter_by(codJugador=clave).first()
    if not j:
        return jsonify({"found": False}), 404

    nombre = (f"{getattr(j, 'nombreJugador', '')} {getattr(j, 'apellidoJugador', '')}").strip()
    jid = getattr(j, 'id', None) or getattr(j, 'idJugador', None)

    return jsonify({"found": True, "id": jid, "codigo": getattr(j, 'codJugador', codigo), "nombre": nombre})

@app.route('/home')
@login_required
def home():
    return render_template('home.html', now=__import__('datetime').datetime.now())

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = Usuario.query.filter_by(username=username, activo=True).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('home'))
        error = 'Usuario o contraseña incorrectos.'
    return render_template('login.html', error=error, now=__import__('datetime').datetime.now())

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/usuarios')
@login_required
@admin_required
def usuarios():
    lista = Usuario.query.order_by(Usuario.username).all()
    return render_template('usuarios.html', usuarios=lista)

@app.route('/usuarios/add', methods=['POST'])
@login_required
@admin_required
def add_usuario():
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()
    rol      = request.form.get('rol', 'operador')
    if not username or not password:
        flash('Usuario y contraseña son requeridos.', 'error')
        return redirect(url_for('usuarios'))
    if Usuario.query.filter_by(username=username).first():
        flash('El nombre de usuario ya existe.', 'error')
        return redirect(url_for('usuarios'))
    db.session.add(Usuario(username=username, password=generate_password_hash(password), rol=rol))
    db.session.commit()
    flash('Usuario creado correctamente.', 'ok')
    return redirect(url_for('usuarios'))

@app.route('/usuarios/edit/<int:id>', methods=['POST'])
@login_required
@admin_required
def edit_usuario(id):
    user = db.session.get(Usuario, id)
    if not user:
        return redirect(url_for('usuarios'))
    user.rol    = request.form.get('rol', user.rol)
    user.activo = request.form.get('activo') == '1'
    nueva_pw    = request.form.get('password', '').strip()
    if nueva_pw:
        user.password = generate_password_hash(nueva_pw)
    db.session.commit()
    flash('Usuario actualizado.', 'ok')
    return redirect(url_for('usuarios'))

@app.route('/usuarios/delete/<int:id>')
@login_required
@admin_required
def delete_usuario(id):
    if id == current_user.id:
        flash('No podés eliminar tu propio usuario.', 'error')
        return redirect(url_for('usuarios'))
    user = db.session.get(Usuario, id)
    if user:
        db.session.delete(user)
        db.session.commit()
    flash('Usuario eliminado.', 'ok')
    return redirect(url_for('usuarios'))

if __name__ == '__main__':
    app.run(debug=True)


