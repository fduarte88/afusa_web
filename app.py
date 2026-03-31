from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from flask import jsonify

app = Flask(__name__)

# Configurar conexión a PostgreSQL
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:0d00@localhost:5432/afusa'
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
    
class TipoAporte(db.Model):
    __tablename__ = 'tipoAporte'
    idTipoAporte = db.Column(db.Integer, primary_key=True)
    descripcion  = db.Column(db.String(100), nullable=False)
    
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

        return redirect(url_for('aportes'))

    aportes = Aporte.query.all()
    aportes_data = []
    for a in aportes:
        fecha_formateada = a.fechaAporte.strftime("%A %d de %B de %Y").capitalize()
        aportes_data.append({
            "jugador": a.jugador.nombreJugador,
            "tipo": a.tipo_aporte.descripcion if a.tipo_aporte else '',
            "descripcion": a.descripcion,
            "importe": a.importe,
            "fecha": fecha_formateada
        })

    return render_template('aportes.html', jugadores=jugadores, tipos=tipos,datetime=datetime, aportes=aportes_data)


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


