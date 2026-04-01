from flask import Flask, render_template, request, redirect, url_for, Response
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from flask import jsonify
import io
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER

app = Flask(__name__)

# Configurar conexión a PostgreSQL
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql+psycopg://postgres:afusa2024@localhost:5432/afusa'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

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
    


# Ruta principal: lista y formulario
@app.route('/')
def index():
    jugadores = Jugador.query.order_by(Jugador.nombreJugador.asc()).all()
    
    # Calcular el siguiente código disponible
    ultimo_codigo = db.session.query(db.func.max(Jugador.codJugador)).scalar()
    siguiente_codigo = (ultimo_codigo or 0) + 1
    
    return render_template('jugadores.html', jugadores=jugadores, siguiente_codigo=siguiente_codigo)

# Crear jugador
@app.route('/add', methods=['POST'])
def add_jugador():
     # Buscar el último código
    ultimo = db.session.query(db.func.max(Jugador.codJugador)).scalar()
    codJugador = (ultimo or 0) + 1  # si no hay jugadores arranca en 1

    nombre = request.form['nombreJugador']
    apellido = request.form['apellidoJugador']
    documento = request.form['numeroDocumento']
    fechaNacimiento = request.form['fechaNacimiento']  # AAAA-MM-DD
    alias = request.form.get('alias')  # opcional

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
def delete_jugador(id):
    jugador = Jugador.query.get_or_404(id)
    db.session.delete(jugador)
    db.session.commit()
    return redirect(url_for('index'))

# Editar jugador (cargar datos en formulario)
@app.route('/edit/<int:id>')
def edit_jugador(id):
    jugadores = Jugador.query.all()
    jugador = Jugador.query.get_or_404(id)
    return render_template('jugadores.html', jugadores=jugadores, jugador_edit=jugador)

# Guardar edición
@app.route('/update/<int:id>', methods=['POST'])
def update_jugador(id):
    jugador = Jugador.query.get_or_404(id)

    jugador.codJugador = request.form['codJugador']
    jugador.nombreJugador = request.form['nombreJugador']
    jugador.apellidoJugador = request.form['apellidoJugador']
    jugador.numeroDocumento = request.form['numeroDocumento']
    jugador.fechaNacimiento = request.form['fechaNacimiento']
    jugador.alias = request.form.get('alias')

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

        nuevo_aporte = Aporte(
            idJugador=jugador_id,                              # FK
            codTipoAporte=(tipo.idTipoAporte if tipo else None),  # FK
            descripcion=(tipo.descripcion if tipo else ''),    # viene de TipoAporte
            fechaAporte=fecha,                                 # del form
            importe=importe                                    # monto
            )   # 'id' es autonumérico y 'adddate' se completa por default en la DB
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
            "fecha": fmt_fecha(a.fechaAporte),
            "fechaRaw": a.fechaAporte.strftime("%Y-%m-%d"),
            "codTipoAporte": a.codTipoAporte,
        })

    egresos_data = []
    for e in Egreso.query.filter(Egreso.fechaEgreso == fecha_eg).order_by(Egreso.id.desc()).all():
        egresos_data.append({
            "id": e.id,
            "tipo": e.tipo_egreso.descripcion if e.tipo_egreso else '',
            "codTipoEgreso": e.codTipoEgreso,
            "descripcion": e.descripcion,
            "importe": e.importe,
            "fecha": fmt_fecha(e.fechaEgreso),
            "fechaRaw": e.fechaEgreso.strftime("%Y-%m-%d"),
        })

    return render_template('caja.html',
        jugadores=jugadores, tipos_ap=tipos_ap, tipos_eg=tipos_eg,
        aportes=aportes_data, egresos=egresos_data, datetime=datetime,
        fecha_ap=fecha_ap_str, fecha_eg=fecha_eg_str)


@app.route('/aportes/delete/<int:id>')
def delete_aporte(id):
    aporte = Aporte.query.get_or_404(id)
    fecha_str = aporte.fechaAporte.strftime("%Y-%m-%d")
    db.session.delete(aporte)
    db.session.commit()
    return redirect(url_for('caja') + f'?tab=aportes&fecha_ap={fecha_str}')

@app.route('/aportes/update/<int:id>', methods=['POST'])
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
                                  fontSize=14, alignment=TA_CENTER, spaceAfter=12)
    msg_style = ParagraphStyle('msg', parent=styles['Normal'],
                               fontSize=11, alignment=TA_CENTER, spaceBefore=30)

    elementos = []
    elementos.append(Paragraph(f"Resumen de la Jornada - {fecha_larga}", titulo_style))
    elementos.append(Spacer(1, 0.4*cm))

    if not aportes:
        elementos.append(Paragraph(f"No hay registros en la fecha seleccionada.", msg_style))
    else:
        data = [['Nombre y Apellido', 'Tipo de Aporte', 'Valor', 'Fecha']]
        total = 0
        for a in aportes:
            jugador = f"{a.jugador.nombreJugador} {a.jugador.apellidoJugador}"
            tipo = a.tipo_aporte.descripcion if a.tipo_aporte else ''
            importe = int(a.importe)
            total += importe
            importe_fmt = f"{importe:,.0f}".replace(',', '.')
            data.append([jugador, tipo, importe_fmt, a.fechaAporte.strftime("%d/%m/%Y")])

        total_fmt = f"{total:,.0f}".replace(',', '.')
        data.append(['', 'TOTAL', total_fmt, ''])

        col_widths = [7*cm, 4.5*cm, 3*cm, 3*cm]
        tabla = Table(data, colWidths=col_widths, repeatRows=1)
        tabla.setStyle(TableStyle([
            ('BACKGROUND',   (0,0), (-1,0), colors.HexColor('#2c5f8a')),
            ('TEXTCOLOR',    (0,0), (-1,0), colors.white),
            ('FONTNAME',     (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE',     (0,0), (-1,0), 10),
            ('ALIGN',        (2,0), (2,-1), 'RIGHT'),
            ('ALIGN',        (3,0), (3,-1), 'CENTER'),
            ('FONTNAME',     (0,1), (-1,-2), 'Helvetica'),
            ('FONTSIZE',     (0,1), (-1,-2), 9),
            ('ROWBACKGROUNDS', (0,1), (-1,-2), [colors.white, colors.HexColor('#f0f4f8')]),
            ('FONTNAME',     (0,-1), (-1,-1), 'Helvetica-Bold'),
            ('BACKGROUND',   (0,-1), (-1,-1), colors.HexColor('#dce8f0')),
            ('GRID',         (0,0), (-1,-1), 0.5, colors.HexColor('#aaaaaa')),
            ('TOPPADDING',   (0,0), (-1,-1), 5),
            ('BOTTOMPADDING',(0,0), (-1,-1), 5),
        ]))
        elementos.append(tabla)

        # Resumen por tipo de aporte
        elementos.append(Spacer(1, 0.8*cm))
        subtitulo_style = ParagraphStyle('subtitulo', parent=styles['Heading2'],
                                         fontSize=11, spaceAfter=6)
        elementos.append(Paragraph("Resumen por Tipo de Aporte", subtitulo_style))

        resumen = {}
        for a in aportes:
            tipo = a.tipo_aporte.descripcion if a.tipo_aporte else 'Sin tipo'
            resumen[tipo] = resumen.get(tipo, 0) + int(a.importe)

        res_data = [['Tipo de Aporte', 'Cantidad', 'Total']]
        conteo = {}
        for a in aportes:
            tipo = a.tipo_aporte.descripcion if a.tipo_aporte else 'Sin tipo'
            conteo[tipo] = conteo.get(tipo, 0) + 1

        for tipo, subtotal in sorted(resumen.items()):
            subtotal_fmt = f"{subtotal:,.0f}".replace(',', '.')
            res_data.append([tipo, str(conteo[tipo]), subtotal_fmt])

        total_res_fmt = f"{total:,.0f}".replace(',', '.')
        res_data.append(['TOTAL', str(len(aportes)), total_res_fmt])

        res_col_widths = [7*cm, 3*cm, 3.5*cm]
        tabla_res = Table(res_data, colWidths=res_col_widths)
        tabla_res.setStyle(TableStyle([
            ('BACKGROUND',    (0,0), (-1,0), colors.HexColor('#2c5f8a')),
            ('TEXTCOLOR',     (0,0), (-1,0), colors.white),
            ('FONTNAME',      (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE',      (0,0), (-1,0), 10),
            ('ALIGN',         (1,0), (-1,-1), 'RIGHT'),
            ('FONTNAME',      (0,1), (-1,-2), 'Helvetica'),
            ('FONTSIZE',      (0,1), (-1,-2), 9),
            ('ROWBACKGROUNDS',(0,1), (-1,-2), [colors.white, colors.HexColor('#f0f4f8')]),
            ('FONTNAME',      (0,-1), (-1,-1), 'Helvetica-Bold'),
            ('BACKGROUND',    (0,-1), (-1,-1), colors.HexColor('#dce8f0')),
            ('GRID',          (0,0), (-1,-1), 0.5, colors.HexColor('#aaaaaa')),
            ('TOPPADDING',    (0,0), (-1,-1), 5),
            ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ]))
        elementos.append(tabla_res)

    doc.build(elementos)
    buffer.seek(0)
    nombre_archivo = f"jornada_{fecha_str}.pdf"
    return Response(buffer, mimetype='application/pdf',
                    headers={'Content-Disposition': f'inline; filename="{nombre_archivo}"'})

@app.route('/egresos', methods=['GET', 'POST'])
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
        return redirect(url_for('caja') + '?tab=egresos')

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
def add_tipo_egreso():
    desc = request.form.get('descripcion', '').strip()
    if desc:
        existe = TipoEgreso.query.filter_by(descripcion=desc).first()
        if not existe:
            db.session.add(TipoEgreso(descripcion=desc))
            db.session.commit()
    return redirect(url_for('caja') + '?tab=egresos')

@app.route('/egresos/tipo/delete/<int:id>')
def delete_tipo_egreso(id):
    tipo = TipoEgreso.query.get_or_404(id)
    if tipo.egresos:
        return redirect(url_for('caja') + '?tab=egresos')
    db.session.delete(tipo)
    db.session.commit()
    return redirect(url_for('caja') + '?tab=egresos')

@app.route('/egresos/delete/<int:id>')
def delete_egreso(id):
    egreso = Egreso.query.get_or_404(id)
    db.session.delete(egreso)
    db.session.commit()
    return redirect(url_for('caja') + '?tab=egresos')

@app.route('/egresos/update/<int:id>', methods=['POST'])
def update_egreso(id):
    egreso  = Egreso.query.get_or_404(id)
    tipo_id = request.form.get('tipo_egreso')
    tipo    = TipoEgreso.query.get(int(tipo_id)) if tipo_id and str(tipo_id).isdigit() else None
    egreso.fechaEgreso   = datetime.strptime(request.form.get('fechaEgreso'), "%Y-%m-%d")
    egreso.codTipoEgreso = tipo.idTipoEgreso if tipo else egreso.codTipoEgreso
    egreso.descripcion   = request.form.get('descripcion', '').strip() or (tipo.descripcion if tipo else '')
    egreso.importe       = request.form.get('importe')
    db.session.commit()
    return redirect(url_for('caja') + '?tab=egresos')

@app.route('/egresos/pdf')
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
                                  fontSize=14, alignment=TA_CENTER, spaceAfter=12)
    msg_style    = ParagraphStyle('msg', parent=styles['Normal'],
                                  fontSize=11, alignment=TA_CENTER, spaceBefore=30)
    subtitulo_style = ParagraphStyle('subtitulo', parent=styles['Heading2'],
                                     fontSize=11, spaceAfter=6)
    elementos = []
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
    titulo_style    = ParagraphStyle('tit',  parent=styles['Title'],  fontSize=15, alignment=TA_CENTER, spaceAfter=4)
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

    elementos = []
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

    # --- BALANCE GENERAL ---
    elementos.append(Spacer(1, 0.8*cm))
    elementos.append(Paragraph("Balance General", subtit_style))
    bal_data = [
        ['Concepto', 'Importe'],
        ['Total Aportes', fmt(total_ap)],
        ['Total Egresos', fmt(total_eg)],
        ['Saldo en Caja', fmt(abs(saldo))],
    ]
    bal_tabla = Table(bal_data, colWidths=[8*cm, 4*cm])
    color_saldo_cel = colors.HexColor('#1a7a1a') if saldo >= 0 else colors.HexColor('#cc0000')
    bal_tabla.setStyle(TableStyle([
        ('BACKGROUND',    (0,0), (-1,0), colors.HexColor('#444444')),
        ('TEXTCOLOR',     (0,0), (-1,0), colors.white),
        ('FONTNAME',      (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE',      (0,0), (-1,-1), 11),
        ('ALIGN',         (1,0), (1,-1), 'RIGHT'),
        ('FONTNAME',      (0,1), (-1,-2), 'Helvetica'),
        ('ROWBACKGROUNDS',(0,1), (-1,-2), [colors.white, colors.HexColor('#f5f5f5')]),
        ('FONTNAME',      (0,-1), (-1,-1), 'Helvetica-Bold'),
        ('BACKGROUND',    (0,-1), (-1,-1), color_saldo_cel),
        ('TEXTCOLOR',     (0,-1), (-1,-1), colors.white),
        ('GRID',          (0,0), (-1,-1), 0.4, colors.HexColor('#aaaaaa')),
        ('TOPPADDING',    (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
    ]))
    elementos.append(bal_tabla)

    doc.build(elementos)
    buffer.seek(0)
    return Response(buffer, mimetype='application/pdf',
                    headers={'Content-Disposition': f'inline; filename="jornada_{fecha_str}.pdf"'})

@app.route('/about')
def about():
    fecha_creacion = datetime.now().strftime("%d/%m/%Y")
    return render_template('about.html', fecha_creacion=fecha_creacion)

@app.route('/api/jugador/<codigo>')
def api_jugador_por_codigo(codigo):
    # si codJugador es numérico en la DB, casteamos
    clave = int(codigo) if codigo.isdigit() else codigo
    j = Jugador.query.filter_by(codJugador=clave).first()
    if not j:
        return jsonify({"found": False}), 404

    nombre = (f"{getattr(j, 'nombreJugador', '')} {getattr(j, 'apellidoJugador', '')}").strip()
    jid = getattr(j, 'id', None) or getattr(j, 'idJugador', None)

    return jsonify({"found": True, "id": jid, "codigo": getattr(j, 'codJugador', codigo), "nombre": nombre})

if __name__ == '__main__':
    app.run(debug=True)


