// «🎓 Aprende»: three sections — music basics, conducting a choir, vocal warm-ups.
// Lessons are written for Coralis (no text copied from books). Examples are drawn with Verovio
// (Api.learn_example, tinyNotation: c4 = middle C quarter, c'8 = an octave up eighth, r4 = rest,
// c4_ma = a syllable) and played with the same grand piano as «Escuchar».

// ---------------------------------------------------------------- the piano for the lessons
const LA = {ctx: null, out: null, buffers: {}, sources: []};
async function laReady(midis) {
  await loadPianoScript();
  if (!LA.ctx) {
    LA.ctx = new (window.AudioContext || window.webkitAudioContext)();
    LA.out = LA.ctx.createGain(); LA.out.gain.value = 0.85; LA.out.connect(LA.ctx.destination);
  }
  if (LA.ctx.state === "suspended") await LA.ctx.resume();
  const avail = Object.keys(window.CORALIS_PIANO).map(Number);
  await Promise.all([...new Set(midis)].filter((m) => !LA.buffers[m]).map(async (midi) => {
    const near = avail.reduce((a, x) => Math.abs(x - midi) < Math.abs(a - midi) ? x : a, avail[0]);
    const res = await fetch(window.CORALIS_PIANO[near]);
    LA.buffers[midi] = {buf: await LA.ctx.decodeAudioData(await res.arrayBuffer()), rate: Math.pow(2, (midi - near) / 12)};
  }));
}
function laNote(midi, at, dur, vol = 0.8) {
  const b = LA.buffers[midi];
  if (!b) return;
  const src = LA.ctx.createBufferSource(), env = LA.ctx.createGain();
  src.buffer = b.buf; src.playbackRate.value = b.rate;
  const len = Math.max(0.08, dur);
  env.gain.setValueAtTime(0.0001, at);
  env.gain.exponentialRampToValueAtTime(vol, at + 0.008);
  env.gain.setValueAtTime(vol, Math.max(at + 0.01, at + len - 0.05));
  env.gain.exponentialRampToValueAtTime(0.0001, at + len + 0.25);
  src.connect(env); env.connect(LA.out);
  src.start(at); src.stop(at + len + 0.3);
  LA.sources.push(src);
}
function laClick(at, strong) {
  const o = LA.ctx.createOscillator(), env = LA.ctx.createGain();
  o.frequency.value = strong ? 1600 : 1000;
  env.gain.setValueAtTime(0.0001, at);
  env.gain.exponentialRampToValueAtTime(strong ? 0.5 : 0.3, at + 0.002);
  env.gain.exponentialRampToValueAtTime(0.0001, at + 0.06);
  o.connect(env); env.connect(LA.out); o.start(at); o.stop(at + 0.08);
  LA.sources.push(o);
}
function laStop() {
  for (const s of LA.sources) { try { s.stop(); } catch (e) { /* done */ } }
  LA.sources = [];
  cancelAnimationFrame(LN.raf); LN.raf = null;
  LN.gen = (LN.gen || 0) + 1;   // any animation still running belongs to an exercise that stopped
}
const NOTE_ES = ["Do", "Re♭", "Re", "Mi♭", "Mi", "Fa", "Fa♯", "Sol", "La♭", "La", "Si♭", "Si"];
const noteName = (midi, octave = true) => NOTE_ES[((midi % 12) + 12) % 12] + (octave ? Math.floor(midi / 12) - 1 : "");

// ---------------------------------------------------------------- the lessons
const LESSONS = {
  musica: {title: "Aprende música", items: [
    {title: "El pentagrama y las claves", html: `
      <p>La música se escribe en el <b>pentagrama</b>: cinco líneas y cuatro espacios. Cuanto más arriba está una nota,
        más aguda suena. Las notas se llaman <b>do, re, mi, fa, sol, la, si</b>, y después vuelve a empezar el do, más agudo.</p>
      <p>La <b>clave</b>, al principio del pentagrama, dice qué nota va en cada línea:</p>
      <ul><li><b>Clave de sol</b> (𝄞): la usan sopranos y contraltos. Su espiral rodea la segunda línea, que es <b>sol</b>.</li>
        <li><b>Clave de fa</b> (𝄢): la usan tenores, barítonos y bajos. Sus dos puntos rodean la cuarta línea, que es <b>fa</b>.</li></ul>
      {{ex:0}}
      <p>La misma escala en clave de fa suena una octava más grave (como cantan los hombres):</p>
      {{ex:1}}
      <p class="hint">Truco: en clave de sol, las líneas de abajo arriba son <b>mi, sol, si, re, fa</b>; los espacios, <b>fa, la, do, mi</b>.
        En clave de fa, las líneas son <b>sol, si, re, fa, la</b>; los espacios, <b>la, do, mi, sol</b>.</p>`,
      ex: [{tiny: "c4_do d4_re e4_mi f4_fa g4_sol a4_la b4_si c'4_do", time: "4/4"},
           {tiny: "C4_do D4_re E4_mi F4_fa G4_sol A4_la B4_si c4_do", time: "4/4", clef: "F"}]},
    {title: "Sostenidos, bemoles y becuadros", html: `
      <p>Entre algunas notas hay una nota intermedia (las teclas negras del piano). Para escribirla se usan las <b>alteraciones</b>:</p>
      <ul><li><b>♯ sostenido</b>: sube la nota medio tono.</li><li><b>♭ bemol</b>: la baja medio tono.</li>
        <li><b>♮ becuadro</b>: anula la alteración y la nota vuelve a ser natural.</li></ul>
      <p>Una alteración escrita junto a una nota vale para esa nota <b>hasta el final del compás</b>.</p>
      {{ex:0}}
      <p class="hint">Medio tono es la distancia más pequeña del piano: de una tecla a la de al lado. De mi a fa y de si a do
        ya hay solo medio tono (no hay tecla negra entre ellas).</p>`,
      ex: [{tiny: "c'4 c#'4 d'4 r4 e'4 e-'4 d'4 r4 f#'4 f'4 g'2", time: "4/4"}]},
    {title: "Figuras y silencios", html: `
      <p>La <b>figura</b> dice cuánto dura la nota. Contamos en <b>tiempos</b> (los pulsos que marcarías con el pie):</p>
      <table class="ln-t"><tr><th>Figura</th><th>Dura</th></tr>
        <tr><td>Redonda 𝅝</td><td>4 tiempos</td></tr><tr><td>Blanca 𝅗𝅥</td><td>2 tiempos</td></tr>
        <tr><td>Negra ♩</td><td>1 tiempo</td></tr><tr><td>Corchea ♪</td><td>½ tiempo</td></tr>
        <tr><td>Semicorchea 𝅘𝅥𝅯</td><td>¼ de tiempo</td></tr></table>
      {{ex:0}}
      <p>Cada figura tiene su <b>silencio</b>, que dura lo mismo pero no se canta. Respetar los silencios es tan importante como
        cantar las notas: ahí se respira.</p>
      {{ex:1}}`,
      ex: [{tiny: "g'1 g'2 g'2 g'4 g'4 g'4 g'4 g'8 g' g' g' g' g' g' g'", time: "4/4"},
           {tiny: "g'4 r4 g'4 r4 g'2 r2 g'8 r8 g'8 r8 g'4 r4", time: "4/4"}]},
    {title: "El compás", html: `
      <p>Los tiempos se agrupan en <b>compases</b>, separados por barras. Los dos números del principio (la <b>cifra</b>)
        dicen cuántos tiempos tiene cada compás. El primer tiempo de cada compás es el más fuerte.</p>
      <ul><li><b>2/4</b>: dos tiempos (fuerte-débil). Marchas.</li><li><b>3/4</b>: tres tiempos (fuerte-débil-débil). Valses, muchos himnos.</li>
        <li><b>4/4</b>: cuatro tiempos. El más común.</li>
        <li><b>6/8</b>: seis corcheas agrupadas de tres en tres: se siente en <b>dos</b> pulsos (como un balanceo).</li></ul>
      {{ex:0}}{{ex:1}}
      <p><b>Anacrusa</b>: cuando la música empieza antes del primer tiempo fuerte (por ejemplo, en el último tiempo). Muchos himnos
        empiezan así: «Su-<b>bli</b>-me gracia» — «Su» es la anacrusa y «bli» cae en el tiempo fuerte.</p>
      {{ex:2}}`,
      ex: [{tiny: "c'4 e' g' r c'4 e' g' r", time: "3/4"},
           {tiny: "c'8 d' e' f'4 e'8 d'4. r4.", time: "6/8"},
           {tiny: "r2 g4_Su c'2_bli e'8_me c'8 e'2_gra d'4_cia", time: "3/4"}]},
    {title: "Puntillo y ligadura", html: `
      <p>El <b>puntillo</b> (un punto después de la nota) le suma la mitad de lo que dura: una blanca con puntillo dura 2 + 1 = <b>3 tiempos</b>;
        una negra con puntillo, 1 + ½ = <b>1½</b>.</p>
      {{ex:0}}
      <p>La <b>ligadura de prolongación</b> une dos notas iguales: se canta una sola nota que dura las dos (sin volver a atacar).
        Sirve para que una nota pase la barra de compás.</p>
      {{ex:1}}
      <p class="hint">Si la línea curva une notas <b>distintas</b> es una <b>ligadura de expresión</b>: se cantan en la misma sílaba,
        sin cortar el sonido (melisma).</p>`,
      ex: [{tiny: "e'2. e'4 d'4. c'8 d'2", time: "4/4"}, {tiny: "g'2 g'2~ g'4 a'4 g'2", time: "4/4"}]},
    {title: "Escalas e intervalos", html: `
      <p>Una <b>escala mayor</b> sigue siempre esta fórmula de distancias: <b>tono, tono, semitono, tono, tono, tono, semitono</b>.
        Suena alegre y brillante. La de do mayor usa solo teclas blancas:</p>
      {{ex:0}}
      <p>La <b>escala menor</b> (natural) cambia la fórmula: tono, semitono, tono, tono, semitono, tono, tono. Suena más seria o triste.</p>
      {{ex:1}}
      <p>Un <b>intervalo</b> es la distancia entre dos notas. Para afinar en coro ayudan mucho estos:</p>
      <ul><li><b>Tercera</b> (do-mi): la base de los acordes.</li><li><b>Quinta</b> (do-sol): muy estable, «hueca».</li>
        <li><b>Octava</b> (do-do): la misma nota, más aguda.</li></ul>
      {{ex:2}}`,
      ex: [{tiny: "c'4 d' e' f' g' a' b' c''", time: "4/4"}, {tiny: "a4 b c' d' e' f' g' a'", time: "4/4"},
           {tiny: "c'2 e'2 c'2 g'2 c'2 c''2", time: "4/4"}]},
    {title: "Armadura y tonalidad", html: `
      <p>La <b>armadura</b> son los sostenidos o bemoles que van al principio de cada pentagrama, junto a la clave. Valen para
        <b>todas</b> esas notas en toda la pieza (en cualquier octava), y dicen la <b>tonalidad</b>.</p>
      <p>Con un bemol (si♭) la pieza está en <b>fa mayor</b> (o re menor): todos los si se cantan si♭.</p>
      {{ex:0}}
      <p class="hint">Truco para la tonalidad mayor: con sostenidos, sube medio tono desde el último sostenido (fa♯ → sol mayor).
        Con bemoles, el penúltimo bemol es la tonalidad (si♭, mi♭ → si♭ mayor). Con un solo bemol, fa mayor.</p>
      <p>En «Escuchar», el botón <b>Tono</b> cambia la tonalidad de todo el himno; Coralis elige la armadura más sencilla.</p>`,
      ex: [{tiny: "f4 g a b- c' d' e' f'", time: "4/4", key: -1}]},
    {title: "Leer un himno a 4 voces", html: `
      <p>En el himnario, las cuatro voces van en <b>dos pentagramas</b>:</p>
      <ul><li><b>Arriba</b> (clave de sol): <b>soprano</b> (plicas hacia arriba, casi siempre la melodía) y <b>contralto</b> (plicas hacia abajo).</li>
        <li><b>Abajo</b> (clave de fa): <b>tenor</b> o barítono (plicas arriba) y <b>bajo</b> (plicas abajo).</li></ul>
      <p>Si dos voces cantan la misma nota, comparten la cabeza con dos plicas. La <b>letra</b> va entre los pentagramas;
        las estrofas, una debajo de otra (1, 2, 3…): canta la línea de tu estrofa.</p>
      <p><b>Signos para no perderse</b>:</p>
      <ul><li><b>𝄆 … 𝄇</b>: repetir lo que está entre las barras.</li>
        <li><b>Casillas 1. y 2.</b>: la primera vez se canta la 1.ª; al repetir, se salta a la 2.ª.</li>
        <li><b>D.C.</b> (da capo): volver al principio. <b>D.S.</b> (dal segno): volver al signo 𝄋.</li>
        <li><b>al Coda</b>: al llegar a «⊕ a la Coda», saltar a la coda. <b>Fine</b>: aquí termina.</li></ul>
      <p class="hint">Con Coralis: abre el himno en «▶ Escuchar», pulsa «Destacar» en tu voz y sigue la partitura mientras suena.
        «Repetir del compás … al …» te deja ensayar el pasaje difícil.</p>`},
    {title: "Práctica: reconoce las notas", widget: "quiz", html: `
      <p>Lee la nota y elige su nombre. Al contestar suena en el piano. Empieza con la clave de tu voz.</p>`},
  ]},
  direccion: {title: "¿Quieres dirigir un coro?", items: [
    {title: "El director y su gesto", html: `
      <p>Dirigir es <b>mostrar con el cuerpo cómo debe sonar la música</b> antes de que suene: cuándo empezar, a qué velocidad,
        qué tan fuerte, cuándo respirar y cuándo terminar. El coro mira tus manos y tu cara; lo que hagas, lo harán.</p>
      <h4>La postura</h4>
      <ul><li>Pies separados más o menos al ancho de los hombros, uno apenas adelantado. El peso en los dos pies.</li>
        <li>Rodillas sueltas (sin trabarlas), pecho alto, hombros hacia atrás pero sin tensión, cabeza derecha.</li>
        <li>Tu postura le dice al coro si estás seguro. Firme, pero nunca rígida.</li></ul>
      <h4>La mano y el brazo</h4>
      <ul><li>El <b>codo separado del cuerpo</b> (un palmo por delante), para que hombro, codo y muñeca se muevan libres.</li>
        <li>La mano como si fueras a <b>dar la mano</b> a alguien: dedos juntos y un poco curvos, pulgar tranquilo. La palma mira
          hacia abajo o un poco de lado, nunca del todo de lado.</li>
        <li>Si eres bajo de estatura, sube un poco el gesto: todo el coro debe verlo, sin que lo tape un atril o el piano.</li>
        <li>Si usas batuta: entre el pulgar y el índice, apoyada en la palma, firme pero sin apretar (apretarla traba la muñeca).</li></ul>
      <p class="hint">Mano izquierda: entradas, dinámica, cortes y expresión. Cuando no la uses, déjala quieta a un lado o junto al
        abdomen; no la dejes «flotando» sin decir nada.</p>`},
    {title: "Practicar frente al espejo", html: `
      <p>El coro no está cuando practicas, así que tu única guía es <b>lo que ves</b>. Practica con espejo, poco y seguido:
        <b>5 a 10 minutos, varias veces al día</b>, mejor que una hora de golpe.</p>
      <ol><li>Antes de mover la mano, revisa la postura: pies, peso, pecho, hombros, cabeza.</li>
        <li>Haz el gesto <b>despacio</b> y mírate. Pregúntate:
          <ul><li>¿Me gusta lo que veo? ¿Parezco seguro?</li><li>¿Está bien colocada la mano? ¿Hay tensión en el brazo o la muñeca?</li>
            <li>¿Es claro? ¿Un cantante sabría en qué tiempo estoy sin oír nada?</li></ul></li>
        <li>Cierra los ojos e imagina el gesto perfecto. Ábrelos y hazlo igual. Repite varias veces.</li>
        <li>Ahora dirige una melodía que conozcas (un himno) <b>cantándola</b>. ¿Tu gesto se parece a la música?</li>
        <li>Dirígela otra vez cantándola solo por dentro, y fíjate en tu cara: también tiene que dirigir.</li></ol>
      <p><b>Para soltarte</b>: imagina que sales al frente de un coro grande que te espera en silencio. Camina, mira a todos,
        levanta las manos, respira y da la entrada. ¿Cómo está tu postura? ¿Y tu cara?</p>
      <p class="hint">Practicar con un compañero ayuda mucho: diríjanse uno al otro y díganse qué se entiende y qué no.
        En Coralis, abre un himno en «▶ Escuchar» con «Ver la partitura» y dirígelo mientras suena.</p>`},
    {title: "El pulso: ictus y rebote", widget: "pattern", preset: {kind: "1"}, html: `
      <p>Todo gesto tiene tres partes: <b>preparación</b> (el camino hacia el tiempo), <b>ictus</b> (el punto exacto del tiempo)
        y <b>rebote</b> (la mano «rebota» después del ictus).</p>
      <ul><li>La mano cae con la <b>muñeca un poco por delante</b>; justo antes del tiempo la mano acelera y la punta de los dedos
          marca el ictus, más o menos entre el esternón y la cintura.</li>
        <li>El <b>rebote</b> sube, pero <b>no más de la mitad</b> de lo que bajaste. Un rebote enorme parece otro tiempo.</li>
        <li>Los dedos no se mueven ni se cierran: la mano entera hace el gesto, como si una gota cayera de la punta de los dedos.</li>
        <li>El tamaño depende del volumen: <i>piano</i> = gesto pequeño, <i>forte</i> = gesto grande. «Dirige solo lo necesario».</li></ul>
      <p>Practica el tiempo hacia abajo con el metrónomo. Cambia «Tamaño» para practicar <i>p</i>, <i>mf</i> y <i>f</i>.</p>`},
    {title: "Los patrones de compás", widget: "pattern", html: `
      <p>Cada compás tiene su dibujo. El <b>primer tiempo siempre va hacia abajo</b> (el más fuerte) y el <b>último hacia arriba</b>
        (prepara el siguiente compás). Así cualquier cantante sabe en qué tiempo vas con solo mirarte.</p>
      <ul><li><b>2 tiempos</b>: abajo, arriba.</li><li><b>3 tiempos</b>: abajo, a la derecha, arriba.</li>
        <li><b>4 tiempos</b>: abajo, a la izquierda (hacia dentro), a la derecha (hacia fuera), arriba.</li>
        <li><b>6/8 rápido</b>: se dirige en 2 (cada tiempo agrupa 3 corcheas).</li></ul>
      <p>El rebote de cada tiempo ya es la preparación del siguiente: no hay paradas, la mano fluye. Practica hasta que el dibujo
        salga solo, sin mirarte la mano.</p>`},
    {title: "Los planos de dirección", html: `
      <p>Un gesto limpio se mueve siempre en los mismos «planos». Un ejercicio muy útil:</p>
      <ol><li>Pega en la pared una cinta (o un hilo) <b>horizontal a la altura de tu cintura</b> y otra <b>vertical</b> que la cruce,
          justo frente a tu hombro derecho.</li>
        <li>Párate de frente a la pared, con la punta de los dedos a un par de centímetros de ella.</li>
        <li>Dirige en 4: el <b>1</b> baja por la línea vertical, el <b>2</b> y el <b>3</b> caen sobre la horizontal, y el <b>4</b> sube otra vez
          por la vertical. Los dedos no se alejan de la pared.</li></ol>
      <p>Al principio cuesta mantener el 2 cerca de la pared (tiende a irse hacia el pecho): ese esfuerzo de hombro y brazo es el
        que le da firmeza al gesto. Un 2 que se va hacia el cuerpo se ve débil.</p>
      <p class="hint">Regla de oro: en cada compás hay <b>un solo</b> movimiento hacia abajo y <b>uno solo</b> hacia arriba. Si exageras
        cada acento, todo parece un primer tiempo y el coro se pierde.</p>`},
    {title: "La entrada: preparar y respirar", html: `
      <p>El coro no puede empezar bien si no sabe <b>cuándo</b> y <b>a qué velocidad</b>. Eso lo da el <b>gesto de preparación</b>:
        un tiempo antes de la entrada, a la velocidad de la pieza.</p>
      <ol><li>Mira al coro y espera silencio. Brazos listos, quietos.</li>
        <li>Da el tono (ver «Dar el tono»).</li>
        <li>Haz el tiempo anterior a la entrada <b>y respira con el coro</b> en ese gesto: tu respiración es la suya.</li>
        <li>El coro entra en el ictus siguiente.</li></ol>
      <p>El gesto de preparación ya dice <b>cómo</b> se va a cantar: si es suave y ligado, prepara suave y redondo; si es fuerte y
        enérgico, prepara con energía. <b>Si el himno empieza con anacrusa</b> (por ejemplo, en el tiempo 3 de un 3/4), prepara con
        el tiempo anterior a la anacrusa (el 2).</p>
      <p class="hint">Error común: preparar más rápido o más lento de lo que se va a cantar. La preparación ya ES el tempo. Y nunca
        des una entrada sin haber mirado antes a quien entra.</p>`},
    {title: "Entradas y cortes en cualquier tiempo", widget: "pattern", preset: {kind: "4", cues: true}, html: `
      <p>En un himno, las voces no siempre entran en el primer tiempo: los hombres responden en el 3, el coro entra después de
        un silencio en el 2… Cada entrada es una <b>invitación a cantar</b>:</p>
      <ul><li><b>Antes</b>: mira a esa voz al menos un tiempo antes. Sin mirada no hay entrada segura.</li>
        <li>El rebote anterior sube más de lo normal, y el tiempo de la entrada se marca un poco más alto (a la altura de la cara),
          moviéndose de lado, no en diagonal.</li>
        <li>El <b>corte</b> en un silencio o una respiración: un pequeño giro que se cierra (puedes juntar pulgar e índice en el
          momento exacto). Debe verse distinto de cualquier otro gesto, y dejar la mano lista para el tiempo siguiente.</li></ul>
      <p>Practica con «Entradas y cortes al azar»: el ejercicio te avisa un compás antes («Prepara: entrada de contraltos en el
        3») y te marca el momento. Mira hacia esa voz imaginaria y da la entrada o el corte sin perder el patrón.</p>`},
    {title: "El corte, el calderón y el final", html: `
      <p>Terminar juntos es tan importante como empezar juntos. El <b>corte</b> es un gesto pequeño y claro en el momento exacto en
        que todos dejan de cantar. Antes del corte, la mano se acelera un poco en su giro: así el coro ve que viene.</p>
      <ul><li>Si la última sílaba termina en consonante («Je-<b>sús</b>»), la consonante va <b>en el corte</b>, todos a la vez.</li>
        <li><b>Calderón</b> (𝄐): la nota dura lo que tú decidas. No detengas la mano del todo: muévela despacio para que se vea que
          la nota sigue viva (más intensa si quieres que crezca, más suave si se apaga). Luego corta, o respira y continúa.</li>
        <li><b>Final que se apaga</b> (<i>morendo</i>): el gesto se hace cada vez más pequeño y lento, la mano baja y se cierra
          suavemente, sin golpe.</li>
        <li>Un final suave pide un corte suave; un final brillante, un corte enérgico. El corte también es música.</li></ul>
      <p class="hint">Decide antes de cada ensayo cuánto dura cada calderón y dónde se respira: lo que no tengas claro tú, el coro no lo hará.</p>`},
    {title: "Independencia de las manos", html: `
      <p>La mano derecha debe marcar el compás <b>sola, sin pensar</b>, para que tu atención y tu mano izquierda queden libres.
        Ejercicios (con el patrón de 4 bien aprendido):</p>
      <ol><li>Marca 4 con la derecha mientras la izquierda sube despacio desde la cintura hasta la altura de los ojos y baja otra vez
          (crescendo y diminuendo).</li>
        <li>Marca 4 con la derecha mientras la izquierda señala, en cada compás, a una voz distinta (sopranos, contraltos, tenores, bajos).</li>
        <li>Marca 4 con la derecha mientras dices en voz alta otra cosa (cuenta hacia atrás de 20 a 1, o recita la letra del himno).</li>
        <li>Marca 3 con la derecha mientras la izquierda hace un gesto de corte en el 2 de cada compás.</li></ol>
      <p>Usos de la mano izquierda: <b>entradas</b> (señalar, o abrir la mano hacia esa voz), <b>dinámica</b> (palma arriba que sube =
        crece; palma abajo que baja = baja el volumen), <b>sostener</b> una nota larga, <b>cortes</b> y pedir atención. A veces las dos
        manos hacen el mismo gesto (en espejo) para una entrada importante; no lo hagas todo el tiempo, pierde fuerza.</p>`},
    {title: "Dinámica, articulación y expresión", widget: "pattern", preset: {kind: "4", art: "marcato"}, html: `
      <ul><li><b>Tamaño del gesto</b> = volumen: gesto grande, coro fuerte; gesto pequeño y cerca del cuerpo, coro suave.</li>
        <li><b>Crescendo</b>: el gesto crece poco a poco; la mano izquierda sube con la palma hacia arriba.
          <b>Diminuendo</b>: el gesto se achica; la mano izquierda baja con la palma hacia abajo.</li>
        <li><b>Legato</b> (ligado): gesto redondo y continuo, sin golpes.</li>
        <li><b>Marcato</b> (marcado): el gesto llega rápido y con firmeza al tiempo y se detiene un instante.</li>
        <li><b>Staccato</b> (corto): gesto pequeño y seco, la mano «salta» de un tiempo al otro.</li>
        <li><b>La cara</b>: al escuchar con atención solemos fruncir el ceño. ¡Cuidado! Tu cara debe inspirar lo que pides.</li>
        <li><b>La letra manda</b>: deja que el texto marque los acentos y las respiraciones. ¿De cuántas maneras puedes decir
          «gracia» o «amor»? Busca la que pide el himno.</li></ul>
      <p>Cambia «Articulación» en el ejercicio y compara cómo se ve cada una.</p>`},
    {title: "Ritardando, accelerando y subdivisión", widget: "pattern", preset: {kind: "4", change: "rit"}, html: `
      <ul><li><b>Ritardando</b> (rit.): cada tiempo dura un poco más. El gesto se hace más grande y pesado; avisa con la mirada
          un compás antes.</li>
        <li><b>Accelerando</b> (accel.): cada tiempo dura un poco menos; el gesto se achica y se aligera.</li>
        <li><b>Subdividir</b>: en tempos muy lentos, marca cada tiempo con un pequeño rebote extra (la «y» de «1 y 2 y»). Úsalo solo
          donde haga falta (por ejemplo, al final de un ritardando).</li></ul>
      <p>En el ejercicio elige «Cambio de tempo»: el metrónomo hace un ritardando (o accelerando) a lo largo de 4 compases y luego
        sigue igual. Trata de que tu gesto lo anticipe, no que lo persiga.</p>`},
    {title: "Dar el tono", widget: "pitch", html: `
      <p>Antes de empezar, el coro necesita oír la tonalidad. Lo más claro es tocar el <b>acorde de la tonalidad</b> y luego la
        <b>nota con la que empieza cada voz</b> (o al menos la de la melodía). Elige la tonalidad del himno (mira la armadura):</p>`},
    {title: "Preparar una pieza y el plan de ensayo", html: `
      <h4>Antes del ensayo, tú solo</h4>
      <ol><li><b>Aprende cada voz</b>: cántala (con el piano o con Coralis: «Destacar» cada voz). Luego cántala mientras suenan las otras.</li>
        <li><b>Imagina cómo debe sonar</b> la pieza bien cantada. Lo que tendrás que enseñar es la diferencia entre eso y lo que oigas.</li>
        <li><b>Dirígela</b> leyendo la letra en voz alta, con sus entradas, cortes y dinámicas.</li>
        <li><b>Marca las dificultades</b>: encierra en un círculo los saltos y ritmos difíciles. Si a ti te cuestan, al coro también.</li>
        <li><b>Escribe tu plan</b>: qué vas a lograr hoy, en qué orden y cuánto tiempo das a cada cosa.</li></ol>
      <h4>En el ensayo</h4>
      <ul><li><b>Empieza con música enseguida</b>. Hablar mucho al principio parece nerviosismo.</li>
        <li>Deja que lean la pieza completa <b>sin parar</b>; si se pierden, sigue dirigiendo para que te alcancen.</li>
        <li><b>Escucha, no cantes</b>: ya sabes dónde están los problemas; anótalos en tu cabeza.</li>
        <li>Al terminar, <b>di algo bueno y verdadero</b> («las sopranos leyeron muy bien»).</li>
        <li>Corrige dando las indicaciones siempre en el mismo orden: <b>página, pentagrama, compás, tiempo y voz</b>
          («Página 2, segundo pentagrama, compás 3, tiempo 1, contraltos»). Así nadie se pierde.</li>
        <li>Al final, vuelvan a cantar la pieza completa para que oigan lo que mejoró.</li></ul>`},
    {title: "Cómo organizar un ensayo", html: `
      <ol><li><b>Empieza y termina a la hora</b>. Avisa el orden de las piezas para que tengan las partituras listas.</li>
        <li><b>Calentamiento</b> (10 minutos): relajación, respiración y vocalización (ver «Ejercicios de vocalización»). Cambia los
          ejercicios de vez en cuando: si siempre son los mismos, dejan de servir.</li>
        <li><b>Lo nuevo, por partes</b>: lee primero el ritmo hablando la letra, luego las notas <b>voz por voz</b>, y después junta
          de dos en dos antes de las cuatro.</li>
        <li><b>Pasajes difíciles</b>: lento primero, luego al tempo. En Coralis, «Repetir del compás … al …» con «Destacar» la voz que lo necesita.</li>
        <li><b>Lo conocido</b>: repasa piezas aprendidas cuidando lo que mejora (afinación, dicción, finales). No empieces siempre
          por el principio: a veces ensaya primero el final.</li>
        <li><b>Termina con algo que salga bien</b>: el coro se va contento y con ganas de volver.</li></ol>
      <p><b>Durante el ensayo</b>: un problema a la vez; habla poco y canta o dirige mucho; da cada indicación una sola vez;
        enséñales a callar en cuanto te detienes; háblale a todo el coro, no solo a una voz; y de vez en cuando déjalos cantar
        sin director, para que se escuchen entre ellos.</p>
      <p class="hint">Manda a cada voz su audio o su video («⬇ Guardar…» → cada voz destacada): estudian en casa y el ensayo rinde el doble.</p>`},
    {title: "Escuchar y corregir", html: `
      <ul><li><b>Afinación</b>: los intervalos que bajan se suelen hacer demasiado grandes y los que suben, demasiado chicos; las
          notas repetidas «se caen»; y la 3.ª y la 7.ª de la escala tienden a quedar bajas. Pide pensarlas «hacia arriba».</li>
        <li><b>Empaste</b>: que la sección suene como una sola voz. Pide escucharse unos a otros, no solo a sí mismos.</li>
        <li><b>Balance</b>: cada sección al mismo volumen dentro de sí, y la melodía un poco por encima de las demás voces.</li>
        <li><b>Vocales</b>: en español son cinco y puras (a, e, i, o, u). Que todos abran igual: así el coro suena unido.</li>
        <li><b>Consonantes</b>: claras y juntas, sobre todo al final de las palabras. La «m», la «n» y la «l» pueden sostenerse:
          dales su tiempo.</li>
        <li><b>La sala</b>: en salas muy «secas» el coro se siente solo y empuja; en salas con mucho eco se pierde la claridad. Ensaya
          a veces en lugares distintos, con aire fresco.</li></ul>
      <p class="hint">No basta decir «están bajos»: busca por qué (cansancio, postura, un salto difícil) y muestra cómo arreglarlo.
        Corrige una cosa a la vez, di qué está bien antes de lo que falta, y repite enseguida para que lo oigan mejorar.</p>`},
    {title: "Cómo acomodar al coro", html: `
      <p>Dónde se para cada cantante cambia cómo suena el coro. Algunas formas (el público está abajo):</p>
      <div class="ln-seats">
        <figure>${seatSVG([["S", "S", "S", "A", "A", "A"], ["T", "T", "T", "B", "B", "B"]])}<figcaption><b>Clásica</b>: mujeres
          adelante, hombres atrás; agudas a un lado, graves al otro. Segura para coros que empiezan.</figcaption></figure>
        <figure>${seatSVG([["S", "S", "A", "A", "S", "S"], ["A", "T", "T", "B", "B", "A"]])}<figcaption><b>Hombres al centro</b>:
          si hay pocos hombres, juntos en el centro suenan más firmes que repartidos.</figcaption></figure>
        <figure>${seatSVG([["T", "T", "B", "B", "T", "T"], ["S", "S", "A", "A", "S", "S"]])}<figcaption><b>Hombres adelante</b>:
          útil cuando quieres oír y trabajar mejor a los hombres.</figcaption></figure>
        <figure>${seatSVG([["S", "A", "T", "B", "S", "A"], ["T", "B", "S", "A", "T", "B"]])}<figcaption><b>En cuartetos</b>: cada uno
          junto a las otras voces. El mejor empaste, pero solo para coros que saben bien su parte.</figcaption></figure>
      </div>
      <ul><li>Las voces que sobresalen, <b>en el centro</b> de su sección, rodeadas de voces que empastan; nunca en las orillas.</li>
        <li>Junto a un cantante inseguro, uno que lea bien.</li>
        <li>Cámbialos de lugar de vez en cuando: cada sitio se oye distinto y aprenden a escuchar.</li></ul>`},
    {title: "La prueba de voz", html: `
      <p>Para conocer a cada cantante (o al recibir a alguien nuevo), haz que vocalice un ejercicio sencillo subiendo y bajando
        por semitonos (por ejemplo «1-3-5-3-1» o «1-2-3-4-5-4-3-2-1» en «Vocalizar con el piano»). Calienta su voz y a la vez te
        deja escuchar casi todo:</p>
      <ol><li><b>Extensión</b>: la nota más aguda y la más grave que alcanza.</li>
        <li><b>Tesitura</b>: dónde canta cómodo (esto decide su voz, más que la extensión).</li>
        <li><b>Timbre</b>: claro u oscuro, ligero o pesado.</li>
        <li><b>Afinación</b>: ¿canta las notas justas?</li>
        <li><b>Legato y staccato</b>: ¿puede ligar sin cortes y cantar notas cortas precisas?</li>
        <li><b>Volumen</b>: ¿puede empezar suave, crecer y volver a suave en una nota larga?</li>
        <li><b>Memoria</b>: tócale una frase corta y que la repita; luego otra más larga.</li></ol>
      <p class="hint">Mucha gente llega nerviosa: una sonrisa y unas palabras amables antes de empezar cambian todo. Si alguien
        canta fuera de su voz porque faltan tenores, no le pidas demasiado: arruinar una voz es una falta grave.</p>`},
    {title: "Lista para el concierto", widget: "checklist", html: `
      <p>Preparar la música es solo una parte. Marca lo que ya está listo (se queda guardado en esta computadora):</p>`},
  ]},
  vocal: {title: "Ejercicios de vocalización", items: [
    {title: "Antes de cantar: postura y relajación", html: `
      <h4>De pie</h4>
      <ul><li>Pies al ancho de los hombros (ni muy abiertos ni juntos), rodillas sueltas, el peso en las dos piernas.</li>
        <li>Pecho abierto sin sacarlo, hombros abajo, cabeza derecha: imagina que llevas un libro en equilibrio sobre la cabeza.</li>
        <li>Prueba: recarga la espalda y los hombros contra una pared; despega los pies poco a poco y quédate con esa sensación.</li></ul>
      <h4>Sentado</h4>
      <ul><li>Derecho, en la orilla de la silla, sin recargarte; los dos pies en el piso, listo para ponerte de pie.</li>
        <li>No cruces las piernas ni los brazos; no te encorves ni hundas el cuello.</li></ul>
      <h4>Soltar tensiones</h4>
      <ul><li><b>Hombros</b>: súbelos hasta las orejas, aguanta 3 segundos y déjalos caer como si pesaran. Luego gíralos hacia atrás.</li>
        <li><b>Cuello</b>: baja la cabeza hacia un hombro y pásala despacio por delante hasta el otro (nunca hacia atrás).</li>
        <li><b>Cara y mandíbula</b>: masajea las mejillas con círculos; deja caer la mandíbula suelta, como en un bostezo.</li>
        <li><b>Lengua</b>: sácala y estírala; luego pásala por los dientes en círculos, con la boca cerrada.</li></ul>`},
    {title: "Calentar el cuerpo", html: `
      <p>Muchos llegan al ensayo cansados o tensos. Unos minutos de movimiento <b>alegran el ambiente</b>, sueltan el cuerpo y
        despiertan la respiración. Explica para qué sirven y hazlos con buen humor:</p>
      <ol><li><b>Alcanzar lo alto</b>: estírate en puntas como si quisieras bajar algo de la repisa más alta; un brazo, el otro, los dos.</li>
        <li><b>Equilibrio</b>: sobre un pie, dibuja círculos en el aire con el otro; cambia de pie.</li>
        <li><b>Masaje en parejas</b>: uno da al otro un masaje suave en hombros y espalda, y luego cambian.</li>
        <li><b>Rodillas sueltas</b>: dobla un poco las rodillas y rebota suave, como un resorte, dejando colgar los brazos.</li>
        <li><b>Caderas</b>: manos en la cintura, dibuja círculos grandes con la cadera hacia un lado y hacia el otro.</li>
        <li><b>Inclinarse</b>: deja caer el tronco hacia delante, despacio, vértebra por vértebra; sube igual, con la cabeza al final.</li>
        <li><b>Bostezar y suspirar</b> (en todos los ensayos): bosteza y estírate a gusto; luego suspira con sonido de lo más agudo a lo
          más grave, como una sirena que se apaga. Sacude los brazos.</li></ol>`},
    {title: "Una rutina de 10 a 15 minutos", widget: "routine", html: `
      <p>Calentar antes del ensayo hace que la voz se canse menos, se oiga más limpia y afine mejor. Un orden que funciona (cámbialo
        según el coro y lo que vayan a cantar, y renueva los ejercicios para que no aburran):</p>`},
    {title: "Respiración", widget: "breath", html: `
      <p>Para cantar se respira <b>bajo y amplio</b>: el aire entra por la nariz (o nariz y boca) y se siente en la cintura, los costados
        y la espalda, <b>sin subir los hombros</b> y sin que se oiga. Al soltar el aire, el pecho no se hunde. No hace falta llenarse
        al máximo: importa más cómo se usa el aire que cuánto se toma.</p>
      <p>Pon las manos en la cintura y sigue el círculo: crece cuando inhalas, se queda quieto cuando sostienes y se achica al exhalar.</p>`},
    {title: "El diafragma", widget: "vocal", preset: {ex: "bon"}, html: `
      <p>El diafragma es el músculo que manda el aire. Con las manos en el abdomen lo sientes moverse: al inhalar baja (la cintura se
        abre), al cantar sube despacio. Ejercicios para despertarlo:</p>
      <ul><li><b>Sorpresa</b>: inhala de golpe, con la boca abierta, como si algo te asustara. Siente cómo se abre la cintura.</li>
        <li><b>Soplar polvo</b>: suelta el aire en soplidos cortos y fuertes («f-f-f-f»), como quitando polvo de un libro.</li>
        <li><b>Reír</b>: «ja-ja-ja» suelto, sintiendo el rebote del abdomen.</li></ul>
      <p>Y con el piano: notas cortas en «bon» donde cada una nace de un pequeño rebote del abdomen.</p>`},
    {title: "Control del aire: sostener la nota", widget: "hold", html: `
      <p>Se trata de gastar <b>solo el aire necesario</b>: el que lo suelta todo al principio se queda sin aire y la nota tiembla
        o se desafina al final. Respira bajo, toma la nota del piano y sostenla en una vocal, parejo, mientras corre el contador.
        Cuando se te acabe el aire, pulsa el botón (o la barra espaciadora). Intenta superar tu récord cada día, sin apretar la garganta.</p>
      <p class="hint">Respira <b>antes</b> de necesitarlo: cuando ya te falta, la nota ya perdió fuerza o afinación.</p>`},
    {title: "Soltar la mandíbula y abrir la garganta", widget: "vocal", preset: {ex: "blablo"}, html: `
      <p>Lo que está sobre la garganta (boca, lengua, mandíbula, paladar) sí lo podemos aflojar, y de eso depende mucho el sonido.</p>
      <ul><li><b>Mandíbula de plomo</b>: di «bla bla bla bla» dejando caer la mandíbula en cada sílaba, sin empujarla.</li>
        <li><b>Hablar rápido en una respiración</b>: «ti-di te-de ta-da to-do tu-du», «pi-bi pe-be pa-ba po-bo pu-bu».</li>
        <li><b>Bostezo cantado</b>: bosteza en «u», «o» y «a», de lo más agudo a lo más grave. Ese espacio del bostezo es el que queremos al cantar.</li>
        <li><b>Lengua</b>: descansa detrás de los dientes de abajo; si se va hacia atrás, el sonido se vuelve apretado.</li></ul>`},
    {title: "Vocalizar con el piano", widget: "vocal", html: `
      <p>Elige un ejercicio y tu voz. El piano da el acorde, respiras, y cantas el dibujo; luego todo sube (o baja) <b>medio tono</b> y
        repites. Canta suave y sin forzar: si un tono se siente difícil, para ahí. Cuando cantan todos juntos, las voces graves
        descansan en los tonos más agudos y las agudas en los más graves.</p>`},
    {title: "Vocales: formarlas y unirlas", widget: "vocal", preset: {ex: "iuia"}, html: `
      <p>Cada vocal tiene su color: la «u» es oscura, la «i» brillante. En el coro hay que <b>acercarlas</b> para que el sonido no
        salte al cambiar de vocal: la «i» un poco más redonda, la «u» un poco más clara, y todas dirigidas hacia adelante.</p>
      <p>Prueba también «mu-mi» (en la lista de ejercicios) y canta una frase de un himno solo con sus vocales, sin consonantes.</p>`},
    {title: "Empaste: el acorde voz por voz", widget: "chord", html: `
      <p>Un coro empasta cuando todos <b>forman la vocal igual</b>: entonces dos o más voces suenan como una sola. El ejercicio: el
        bajo canta su nota en una vocal; luego entra el barítono, después la contralto y al final la soprano, cada una con la
        <b>misma vocal y el mismo volumen</b>, escuchando que el acorde quede limpio. La voz que «se oye» por encima, ajusta.</p>
      <p class="hint">Hazlo en sección también: una persona canta «u», y los demás entran de uno en uno sin que se note quién entró.
        Graba al coro de vez en cuando: se oye mejor desde fuera.</p>`},
    {title: "De grave a agudo sin quiebres", widget: "vocal", preset: {ex: "lameo"}, html: `
      <p>Una voz pareja no cambia de color de golpe al pasar de las notas graves a las agudas («quiebre» o «paso»). Ayuda mucho
        <b>empezar arriba y bajar</b>: llevas a las notas graves el sonido ligero de las agudas. Por eso estos ejercicios bajan medio
        tono cada vez.</p>
      <p class="hint">Se logra con práctica regular y sin forzar. Si la voz se quiebra, más suave y más despacio.</p>`},
    {title: "Resonancia", widget: "vocal", preset: {ex: "ming"}, html: `
      <p>La voz se amplifica en la cara, la nariz, la boca y el pecho. La <b>m</b>, la <b>n</b>, la <b>l</b>, la <b>v</b> y la <b>ng</b> ayudan a
        encontrar esa vibración. Para ganar volumen sin gritar: empieza suave y crece poco a poco, con todo suelto.</p>
      <p>Prueba también «ding-dong» (en la lista): como campanas que siguen sonando.</p>`},
    {title: "Labios", widget: "vocal", preset: {ex: "tiptop"}, html: `
      <p>Los labios dan la forma final al sonido, como las manos al barro. Si están rígidos, estirados o con el labio de abajo hacia
        fuera, las vocales se deforman. Suéltalos: vibra los labios («brrr»), di «pi-po-pa» exagerando la forma, y canta
        «ma-ma-ma» con labios blandos.</p>`},
    {title: "Dinámica: crecer y bajar", widget: "vocal", preset: {ex: "messa"}, html: `
      <p>Un buen <i>crescendo</i> crece <b>parejo</b>, no de golpe al final; y un buen <i>piano</i> suena lleno, no soplado. Cuando el sonido
        suave sale con mucho aire, es que se escapa aire sin sonido: más apoyo, menos volumen.</p>
      <p>En cada nota del ejercicio: suave → fuerte → suave, sin que la nota suba ni baje de afinación.</p>`},
    {title: "Agilidad", widget: "vocal", preset: {ex: "taka", accel: true}, html: `
      <p>Una voz ágil se mueve rápido y segura, sin perder el buen sonido. Empieza lento (♩ = 60) y deja que el ejercicio acelere en
        cada repetición. Si el sonido se ensucia, baja la velocidad: la rapidez nunca a costa del sonido.</p>
      <p>Prueba también «ba-na», «da-me-ni-po-tu-la-be» y los tresillos «ma-la-ga».</p>`},
    {title: "Afinación y oído", widget: "vocal", preset: {ex: "fifth", piano: "first"}, html: `
      <ul><li>Los intervalos que <b>bajan</b> se hacen demasiado grandes; los que <b>suben</b>, demasiado chicos.</li>
        <li>Las <b>notas repetidas</b> se caen: mantén la energía en cada una (ejercicio «notas repetidas»).</li>
        <li>La <b>3.ª y la 7.ª</b> de la escala suelen quedar bajas: piénsalas altas.</li>
        <li>Antes de cantar cada nota, <b>escúchala por dentro</b>.</li></ul>
      <p>Aquí el piano da <b>solo el primer acorde</b>: después, cada repetición sube medio tono y tú lo encuentras de oído. Con
        «a capella, y comprueba la última nota», el piano te dice al final si sigues afinado.</p>`},
    {title: "Ritmo", widget: "vocal", preset: {ex: "synco"}, html: `
      <p>Cantar a tiempo es tan importante como cantar afinado. Marca el pulso con el pie (o aplaude en los tiempos 2 y 4) y canta
        las notas justas, cortas y precisas. Empieza lento; cuando salga sin pensar, sube la velocidad.</p>
      <p>Prueba también los tresillos «ma-la-ga» y «ta-ka» acelerando.</p>`},
    {title: "Dicción: vocales y consonantes", widget: "vocal", preset: {ex: "mnl"}, html: `
      <p>La letra se entiende por las <b>consonantes</b> y el sonido lo llevan las <b>vocales</b>.</p>
      <ul><li>Vocales: las cinco del español, puras y con la boca formada igual en todo el coro.</li>
        <li>Consonantes: con energía y todos a la vez, sobre todo al final de las palabras.</li>
        <li>La <b>m</b>, la <b>n</b> y la <b>l</b> se pueden sostener con sonido: dales su tiempo, que no desaparezcan («Se-ñor»,
          «a-mor», «Je-sús»).</li>
        <li>Para practicarlo: canta en una nota, despacio y luego rápido, «las con-so-nan-tes cla-ras, las vo-ca-les lar-gas».</li></ul>`},
    {title: "Respirar en medio de la frase", widget: "vocal", preset: {ex: "breath"}, html: `
      <p>A veces hay que respirar sin cortar la música: canta la nota, córtala justo para tomar aire rápido, y <b>vuelve a la misma
        nota sin golpearla</b> (no más fuerte que antes). El ejercicio deja un pequeño silencio para respirar entre cada «na».</p>`},
    {title: "Cuidar la voz", html: `
      <ul><li><b>Agua</b>: bebe a lo largo del día, no solo antes de cantar.</li>
        <li><b>No gritar ni carraspear</b>: si sientes algo en la garganta, traga saliva o toma agua.</li>
        <li><b>Descanso</b>: dormir bien es parte del ensayo. Una voz cansada se lastima más fácil.</li>
        <li><b>Calentar y enfriar</b>: antes de cantar, vocaliza; después de un ensayo largo, unos «mmm» suaves bajando.</li>
        <li><b>Si duele, para</b>. La ronquera de más de dos semanas hay que verla con un médico.</li></ul>`},
  ]},
};

// ---------------------------------------------------------------- the screen
const LN = {tab: "musica", item: 0, raf: null, cache: {}};
function openLearn(tab = LN.tab) {
  show("home", false); show("learn", true);
  LN.tab = tab; renderLearnTabs(); showLesson(tab === LN.tab ? LN.item : 0);
}
function closeLearn() { laStop(); show("learn", false); show("home", true); }
function renderLearnTabs() {
  $("lnTabs").innerHTML = Object.entries(LESSONS).map(([k, s]) =>
    `<button class="btn ${k === LN.tab ? "primary" : ""}" onclick="setLearnTab('${k}')">${esc(s.title)}</button>`).join("");
}
function setLearnTab(k) { laStop(); LN.tab = k; renderLearnTabs(); showLesson(0); }
function showLesson(i) {
  laStop();
  const sec = LESSONS[LN.tab];
  LN.item = Math.max(0, Math.min(sec.items.length - 1, i));
  $("lnList").innerHTML = sec.items.map((it, j) =>
    `<button class="${j === LN.item ? "on" : ""}" onclick="showLesson(${j})">${j + 1}. ${esc(it.title)}</button>`).join("");
  const it = sec.items[LN.item];
  let html = it.html.replace(/\{\{ex:(\d+)\}\}/g, (_, n) => `<div class="ln-ex" data-ex="${n}"><p class="hint">Dibujando…</p></div>`);
  html += `<div id="lnWidget"></div>
    <div class="row" style="justify-content:space-between;margin-top:18px">
      <button class="btn" ${LN.item ? "" : "disabled"} onclick="showLesson(${LN.item - 1})">◀ Anterior</button>
      <button class="btn" ${LN.item < sec.items.length - 1 ? "" : "disabled"} onclick="showLesson(${LN.item + 1})">Siguiente ▶</button></div>`;
  $("lnBody").innerHTML = `<h3>${esc(it.title)}</h3>${html}`;
  for (const box of $("lnBody").querySelectorAll(".ln-ex")) fillExample(box, it.ex[+box.dataset.ex]);
  if (it.widget) WIDGETS[it.widget](it.preset || {});
  $("lnBody").scrollTop = 0;
}
async function exampleData(spec) {
  const key = JSON.stringify(spec);
  if (!LN.cache[key]) LN.cache[key] = await pywebview.api.learn_example(spec);
  return LN.cache[key];
}
async function fillExample(box, spec) {
  const r = await exampleData(spec);
  if (!r || !r.ok) { box.innerHTML = `<p class="hint">${esc((r && r.error) || "No se pudo dibujar.")}</p>`; return; }
  box.innerHTML = `<div class="ln-svg">${r.svg}</div><button class="btn" type="button">▶ Escuchar</button>`;
  box.querySelector("button").onclick = () => playExample(r.notes, spec.time === "6/8" ? 100 : 80);
}
async function playExample(notes, bpm) {
  laStop();
  await laReady(notes.map((n) => n[2]));
  const sq = 60 / bpm, t0 = LA.ctx.currentTime + 0.1;
  for (const [off, dur, midi] of notes) laNote(midi, t0 + off * sq, dur * sq * 0.95);
}

// ---------------------------------------------------------------- practice: name the note
const QUIZ_POOL = {
  G: ["c", "d", "e", "f", "g", "a", "b", "c'", "d'", "e'", "f'", "g'", "a'"],
  F: ["EE", "FF", "GG", "AA", "BB", "C", "D", "E", "F", "G", "A", "B", "c"],
};
const QZ = {clef: "G", note: null, ok: 0, total: 0, answered: false};
const LETTER_ES = {c: "Do", d: "Re", e: "Mi", f: "Fa", g: "Sol", a: "La", b: "Si"};
function quizWidget() {
  $("lnWidget").innerHTML = `<div class="ln-widget">
    <div class="row" style="gap:8px"><label>Clave <select id="qzClef"><option value="G">de sol (sopranos, contraltos)</option>
      <option value="F">de fa (tenores, barítonos, bajos)</option><option value="both">las dos</option></select></label>
      <span class="hint" id="qzScore"></span></div>
    <div class="ln-svg qz-note" id="qzNote"></div>
    <div class="row qz-btns" style="gap:6px;justify-content:center">${["Do", "Re", "Mi", "Fa", "Sol", "La", "Si"].map((n) =>
      `<button class="btn" onclick="quizAnswer('${n}')">${n}</button>`).join("")}</div>
    <p id="qzMsg" style="text-align:center;font-size:18px;min-height:26px"></p></div>`;
  $("qzClef").value = QZ.clefChoice || "G";
  $("qzClef").onchange = () => { QZ.clefChoice = $("qzClef").value; quizNext(); };
  quizNext();
}
async function quizNext() {
  const choice = $("qzClef").value;
  const clef = choice === "both" ? (Math.random() < 0.5 ? "G" : "F") : choice;
  const pool = QUIZ_POOL[clef];
  let name;
  do { name = pool[Math.floor(Math.random() * pool.length)]; } while (QZ.note && name === QZ.note.name && pool.length > 1);
  QZ.note = {name, clef}; QZ.answered = false;
  $("qzMsg").textContent = "";
  const r = await exampleData({tiny: name + "1", clef, scale: 60});
  if (QZ.note.name !== name) return;
  $("qzNote").innerHTML = r && r.ok ? r.svg : "";
  QZ.note.midi = r && r.ok ? r.notes[0][2] : 60;
  $("qzScore").textContent = QZ.total ? `${QZ.ok} de ${QZ.total} bien` : "";
}
async function quizAnswer(n) {
  if (!QZ.note || QZ.answered) return;
  QZ.answered = true;
  const right = LETTER_ES[QZ.note.name.replace(/[^a-gA-G]/g, "")[0].toLowerCase()];
  QZ.total++; if (n === right) QZ.ok++;
  $("qzMsg").innerHTML = n === right ? `<b style="color:var(--accent)">✓ ¡Bien! Es ${right}.</b>` : `✗ Es <b>${right}</b>.`;
  $("qzScore").textContent = `${QZ.ok} de ${QZ.total} bien`;
  await laReady([QZ.note.midi]); laNote(QZ.note.midi, LA.ctx.currentTime + 0.02, 1.2);
  setTimeout(() => { if (QZ.answered && $("qzNote")) quizNext(); }, n === right ? 1100 : 2200);
}

// ---------------------------------------------------------------- conducting patterns
const PATTERNS = {   // where each beat's ictus is, in a 0..1 box
  "1": {beats: 1, pts: [[0.5, 0.82]], sub: 1, label: "1 tiempo (solo el pulso)"},
  "2": {beats: 2, pts: [[0.5, 0.82], [0.58, 0.28]], sub: 1, label: "2 tiempos (2/4, 2/2)"},
  "3": {beats: 3, pts: [[0.5, 0.82], [0.84, 0.62], [0.55, 0.24]], sub: 1, label: "3 tiempos (3/4)"},
  "4": {beats: 4, pts: [[0.5, 0.84], [0.16, 0.62], [0.84, 0.62], [0.55, 0.22]], sub: 1, label: "4 tiempos (4/4)"},
  "6": {beats: 2, pts: [[0.5, 0.82], [0.58, 0.28]], sub: 3, label: "6/8 en 2 (cada tiempo = 3 corcheas)"},
};
const CUE_VOICES = ["sopranos", "contraltos", "tenores", "bajos", "todo el coro"];
const PT = {};
function patternWidget(preset = {}) {
  $("lnWidget").innerHTML = `<div class="ln-widget">
    <div class="row" style="gap:10px;flex-wrap:wrap">
      <label>Compás <select id="ptKind">${Object.entries(PATTERNS).map(([k, p]) => `<option value="${k}">${p.label}</option>`).join("")}</select></label>
      <label>Velocidad <input type="number" id="ptBpm" min="30" max="180" value="72" style="width:64px"></label>
      <label>Articulación <select id="ptArt"><option value="legato">legato (ligado)</option><option value="marcato">marcato</option>
        <option value="staccato">staccato (corto)</option></select></label>
      <label>Tamaño <select id="ptSize"><option value="p">p (suave)</option><option value="mf" selected>mf</option><option value="f">f (fuerte)</option></select></label></div>
    <div class="row" style="gap:10px;flex-wrap:wrap;margin-top:8px">
      <label>Cambio de tempo <select id="ptChange"><option value="">ninguno</option><option value="rit">ritardando (en 4 compases)</option>
        <option value="accel">accelerando (en 4 compases)</option></select></label>
      <label><input type="checkbox" id="ptCues"> Entradas y cortes al azar</label>
      <label><input type="checkbox" id="ptClick" checked> Metrónomo</label>
      <button class="btn primary" id="ptGo">▶ Empezar</button></div>
    <canvas id="ptCanvas" width="520" height="460" style="width:100%;max-width:520px;display:block;margin:10px auto;background:#fff;border-radius:12px;border:1px solid var(--line)"></canvas>
    <p class="hint" style="text-align:center">Sigue el punto con tu mano derecha. El número grande es el tiempo que suena.</p></div>`;
  $("ptKind").value = preset.kind || "4";
  if (preset.art) $("ptArt").value = preset.art;
  if (preset.change) $("ptChange").value = preset.change;
  if (preset.cues) $("ptCues").checked = true;
  $("ptGo").onclick = () => LN.raf ? (laStop(), $("ptGo").textContent = "▶ Empezar", drawPattern(null)) : startPattern();
  for (const id of ["ptKind", "ptArt", "ptSize", "ptChange", "ptCues"]) $(id).onchange = () => { if (LN.raf) startPattern(); else drawPattern(null); };
  drawPattern(null);
}
function patternPoint(p, beat, f, art = "legato", size = 1) {
  // from this ictus to the next one: a rebound (up), then down into the next ictus
  const A = p.pts[beat], B = p.pts[(beat + 1) % p.beats];
  let x, y;
  if (p.beats === 1) {   // one beat: straight down and up again (the rebound is half the fall)
    const h = 0.42 * Math.sin(Math.PI * f) ** (art === "legato" ? 1 : 0.6);
    x = A[0]; y = A[1] - h;
  } else {
    const lift = (beat === p.beats - 1 ? 0.12 : 0.22) * (art === "staccato" ? 0.6 : 1);
    const C = [(A[0] + B[0]) / 2, Math.min(A[1], B[1]) - lift];
    // legato: slow at the top, fast into the ictus; marcato: gets there quickly and waits;
    // staccato: a small quick jump and a stop at the ictus
    const e = art === "marcato" ? Math.min(1, (f / 0.7) ** 2) : art === "staccato" ? Math.min(1, f / 0.45) : f * f * (3 - 2 * f);
    x = (1 - e) * (1 - e) * A[0] + 2 * (1 - e) * e * C[0] + e * e * B[0];
    y = (1 - e) * (1 - e) * A[1] + 2 * (1 - e) * e * C[1] + e * e * B[1];
  }
  const k = size * (art === "staccato" ? 0.8 : 1);   // the gesture's size around its centre
  return [0.5 + (x - 0.5) * k, 0.6 + (y - 0.6) * k];
}
function sizeOf() { return {p: 0.55, mf: 0.8, f: 1}[$("ptSize").value] || 0.8; }
function drawPattern(state) {
  const cv = $("ptCanvas"); if (!cv) return;
  const c = cv.getContext("2d"), W = cv.width, H = cv.height, p = PATTERNS[$("ptKind").value];
  const art = $("ptArt").value, size = sizeOf();
  c.clearRect(0, 0, W, H);
  c.strokeStyle = "#d8ddd9"; c.lineWidth = 3; c.beginPath();
  for (let b = 0; b < p.beats; b++) for (let k = 0; k <= 40; k++) {
    const [x, y] = patternPoint(p, b, k / 40, "legato", size);
    if (b === 0 && k === 0) c.moveTo(x * W, y * H); else c.lineTo(x * W, y * H);
  }
  c.stroke();
  c.strokeStyle = "#bbb"; c.setLineDash([6, 6]); c.beginPath();
  const base = (0.6 + (0.84 - 0.6) * size) * H + 14;
  c.moveTo(30, base); c.lineTo(W - 30, base); c.stroke(); c.setLineDash([]);
  p.pts.forEach((pt, i) => {
    const [x, y] = patternPoint(p, i === 0 ? p.beats - 1 : i - 1, 1, "legato", size);
    c.fillStyle = state && state.beat === i ? "#2f6f5e" : "#9aa5a0";
    c.font = `bold ${state && state.beat === i ? 34 : 22}px -apple-system, Segoe UI, sans-serif`;
    c.textAlign = "center"; c.fillText(String(i + 1), x * W + (x < 0.5 ? -28 : 28), y * H + 8);
  });
  if (state) {
    const [x, y] = patternPoint(p, state.beat, state.f, art, size);
    c.fillStyle = "#2f6f5e"; c.beginPath(); c.arc(x * W, y * H, 13, 0, 2 * Math.PI); c.fill();
    if (state.msg) {
      c.fillStyle = state.now ? "#b4471f" : "#2f6f5e";
      c.font = `bold ${state.now ? 28 : 20}px -apple-system, Segoe UI, sans-serif`; c.textAlign = "center";
      c.fillText(state.msg, W / 2, 34);
    }
    if (state.tempo) { c.fillStyle = "#777"; c.font = "15px -apple-system, Segoe UI, sans-serif"; c.textAlign = "right"; c.fillText(state.tempo, W - 14, H - 12); }
  }
}
async function startPattern() {
  laStop();
  await laReady([]);
  const p = PATTERNS[$("ptKind").value], change = $("ptChange").value;
  const bpm = Math.max(30, Math.min(180, +$("ptBpm").value || 72)), T0 = 60 / bpm;
  // when each beat falls: steady, or slowing down / speeding up over 4 measures, then steady
  const ramp = 4 * p.beats, times = [0], lens = [];
  for (let k = 0; k < 600; k++) {
    let T = T0;
    if (change && k >= p.beats) {   // one steady measure first
      const f = Math.min(1, (k - p.beats) / ramp);
      T = change === "rit" ? T0 * (1 + 0.6 * f) : T0 / (1 + 0.5 * f);
    }
    lens.push(T); times.push(times[k] + T);
  }
  // entries and cut-offs at random: announced one measure before
  const cues = {};
  if ($("ptCues").checked && p.beats > 1) {
    for (let m = 2; m < 150; m += 2) cues[m] = {beat: 1 + Math.floor(Math.random() * p.beats), cut: Math.random() < 0.4,
                                                 who: CUE_VOICES[Math.floor(Math.random() * CUE_VOICES.length)]};
  }
  const t0 = LA.ctx.currentTime + 0.3;
  if ($("ptClick").checked) {
    for (let k = 0; k < 600; k++) {
      laClick(t0 + times[k], k % p.beats === 0);
      for (let s = 1; s < p.sub; s++) laClick(t0 + times[k] + s * lens[k] / p.sub, false);
    }
  }
  $("ptGo").textContent = "⏹ Parar";
  let k = 0;
  const gen = LN.gen, frame = () => {
    if (gen !== LN.gen) return;   // another exercise took over
    const el = LA.ctx.currentTime - t0;
    while (k + 1 < times.length && times[k + 1] <= el) k++;
    const f = el < 0 ? 0 : Math.min(1, (el - times[k]) / lens[k]);
    const beat = k % p.beats, measure = Math.floor(k / p.beats) + 1;
    let msg = "", now = false;
    const cue = cues[measure + 1], here = cues[measure];
    const say = (c) => c.cut ? `corte de ${c.who} en el ${c.beat}` : `entrada de ${c.who} en el ${c.beat}`;
    if (here && beat + 1 === here.beat) { msg = here.cut ? "¡Corte!" : `¡Entrada de ${here.who}!`; now = true; }
    else if (here && beat + 1 < here.beat) msg = "Ahora: " + say(here);
    else if (cue) msg = "Prepara: " + say(cue);
    const bpmNow = Math.round(60 / lens[k]);
    drawPattern({beat: el < 0 ? 0 : beat, f: el < 0 ? 0 : f, msg, now, tempo: change ? `♩ = ${bpmNow}` : ""});
    LN.raf = requestAnimationFrame(frame);
  };
  LN.raf = requestAnimationFrame(frame);
}

// ---------------------------------------------------------------- how to place the choir (a drawing)
function seatSVG(rows) {
  const col = {S: "#d9534f", A: "#e5a03a", T: "#3f8fd2", B: "#2f6f5e"}, w = 34, h = 30, gap = 6;
  const W = rows[0].length * (w + gap) + 20, H = rows.length * (h + gap) + 44;
  let out = `<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" xmlns="http://www.w3.org/2000/svg" font-family="-apple-system, Segoe UI, sans-serif">`;
  rows.slice().reverse().forEach((row, r) => row.forEach((v, i) => {
    const x = 10 + i * (w + gap), y = 8 + r * (h + gap);
    out += `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="7" fill="${col[v]}"/><text x="${x + w / 2}" y="${y + 20}" text-anchor="middle" fill="#fff" font-weight="700" font-size="15">${v}</text>`;
  }));
  out += `<rect x="${W / 2 - 14}" y="${H - 26}" width="28" height="18" rx="4" fill="#777"/><text x="${W / 2}" y="${H - 13}" text-anchor="middle" fill="#fff" font-size="11">dir.</text></svg>`;
  return out;
}

// ---------------------------------------------------------------- concert checklist (kept in this computer)
const CHECKLIST = [
  ["Semanas antes", ["Elegir las piezas y el orden del programa", "Acompañante (piano u órgano) confirmado", "Lugar, fecha y hora confirmados",
    "Avisos y carteles (iglesia, redes, radio)", "Programa impreso o en pantalla", "Ensayo general en el lugar del concierto"]],
  ["El día", ["Piano afinado", "Atriles, sillas, tarimas y podio en su lugar", "Sonido y micrófonos probados", "Luces",
    "Alguien que reciba al público y reparta programas", "Grabación (alguien a cargo)", "Agua para el coro"]],
  ["Antes de salir", ["Calentamiento de voces (10 minutos)", "Repasar entradas difíciles y el orden", "Partituras en orden en cada carpeta"]],
];
function checklistWidget() {
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem("coralis.checklist") || "{}"); } catch (e) { saved = {}; }
  $("lnWidget").innerHTML = `<div class="ln-widget">${CHECKLIST.map(([group, items], g) => `<h4 style="margin:6px 0">${esc(group)}</h4>
    ${items.map((it, i) => `<label style="display:flex;gap:8px;align-items:center;margin:4px 0"><input type="checkbox" data-k="${g}-${i}"
      ${saved[`${g}-${i}`] ? "checked" : ""}> ${esc(it)}</label>`).join("")}`).join("")}
    <div class="row" style="justify-content:flex-end;margin-top:8px"><button class="btn" id="ckReset">Empezar de nuevo</button></div></div>`;
  const store = () => {
    const out = {};
    $("lnWidget").querySelectorAll("input[data-k]").forEach((el) => { if (el.checked) out[el.dataset.k] = true; });
    try { localStorage.setItem("coralis.checklist", JSON.stringify(out)); } catch (e) { /* only a convenience */ }
  };
  $("lnWidget").querySelectorAll("input[data-k]").forEach((el) => { el.onchange = store; });
  $("ckReset").onclick = () => { $("lnWidget").querySelectorAll("input[data-k]").forEach((el) => { el.checked = false; }); store(); };
}

// ---------------------------------------------------------------- give the pitch
function pitchWidget() {
  $("lnWidget").innerHTML = `<div class="ln-widget"><div class="row" style="gap:10px;flex-wrap:wrap">
    <label>Tonalidad <select id="gpKey">${NOTE_ES.map((n, i) => `<option value="${i}">${n}</option>`).join("")}</select></label>
    <label>Modo <select id="gpMode"><option value="major">mayor</option><option value="minor">menor</option></select></label>
    <button class="btn primary" onclick="givePitch(false)">▶ Acorde</button>
    <button class="btn" onclick="givePitch(true)">▶ Acorde y notas</button></div>
    <p class="hint">«Acorde y notas»: el acorde, y luego la nota de cada voz de abajo arriba (bajo, barítono, contralto, soprano), sosteniéndose.</p></div>`;
}
async function givePitch(notes) {
  laStop();
  const k = +$("gpKey").value, third = $("gpMode").value === "minor" ? 3 : 4;
  const root = 48 + k;   // the chord around the middle of the choir
  const chord = [root - 12, root, root + third, root + 7];   // bass, baritone, alto, soprano
  const voices = [root - 12, root - 5, root + third, root + 12];   // bass root, baritone fifth, alto third, soprano root
  await laReady(chord.concat(voices));
  const t = LA.ctx.currentTime + 0.05;
  chord.forEach((m) => laNote(m, t, 1.6, 0.6));
  if (notes) voices.forEach((m, i) => laNote(m, t + 2 + i * 0.9, 3.6 - i * 0.9 + 1.2, 0.7));
}

// ---------------------------------------------------------------- breathing
const BREATHS = [
  {name: "Calma: inhala 4 · sostén 4 · exhala 6", phases: [["Inhala", 4], ["Sostén", 4], ["Exhala", 6]], cycles: 4},
  {name: "Apoyo: inhala 4 · exhala en «sss» 12", phases: [["Inhala", 4], ["Exhala «sss»", 12]], cycles: 3},
  {name: "Aire rápido: inhala 2 · exhala en «fff» 8", phases: [["Inhala", 2], ["Exhala «fff»", 8]], cycles: 4},
  {name: "Largo: inhala 4 · sostén 7 · exhala 8", phases: [["Inhala", 4], ["Sostén", 7], ["Exhala", 8]], cycles: 3},
  {name: "Oler una flor: tres pequeñas inhalaciones · exhala 6", phases: [["Inhala (1)", 1], ["Inhala (2)", 1], ["Inhala (3)", 1], ["Exhala lento", 6]], cycles: 4},
  {name: "Diafragma: inhala 3 · cuatro soplidos cortos «f-f-f-f»", phases: [["Inhala", 3], ["«f»", 1], ["«f»", 1], ["«f»", 1], ["«f»", 1]], cycles: 4},
];
function breathWidget() {
  $("lnWidget").innerHTML = `<div class="ln-widget"><div class="row" style="gap:10px;flex-wrap:wrap">
    <label>Ejercicio <select id="brKind">${BREATHS.map((b, i) => `<option value="${i}">${esc(b.name)} (${b.cycles} veces)</option>`).join("")}</select></label>
    <label><input type="checkbox" id="brTick" checked> Tic cada segundo</label>
    <button class="btn primary" id="brGo">▶ Empezar</button></div>
    <div class="br-stage"><div class="br-circle" id="brCircle"></div><div class="br-text"><div id="brPhase">Listo</div><div id="brCount"></div></div></div></div>`;
  $("brGo").onclick = () => LN.raf ? stopBreath() : startBreath();
}
function stopBreath() { laStop(); $("brGo").textContent = "▶ Empezar"; $("brPhase").textContent = "Listo"; $("brCount").textContent = ""; setCircle(0.45); }
function setCircle(s) { const el = $("brCircle"); if (el) el.style.transform = `scale(${s})`; }
async function startBreath() {
  laStop(); await laReady([]);
  const b = BREATHS[+$("brKind").value];
  const steps = [];
  let t = 1.5;   // a moment to get ready
  for (let c = 0; c < b.cycles; c++) b.phases.forEach(([label, secs], ph) => { steps.push({label, t, secs, cycle: c, ph}); t += secs; });
  const t0 = LA.ctx.currentTime, end = t;
  if ($("brTick").checked) for (let s = 1; s < end; s++) laClick(t0 + s + 0.5, steps.some((x) => Math.abs(x.t - (s + 0.5)) < 0.01));
  $("brGo").textContent = "⏹ Parar";
  let from = 0.45, prevKey = null;
  const gen = LN.gen, frame = () => {
    if (gen !== LN.gen) return;   // another exercise took over
    const el = LA.ctx.currentTime - t0;
    if (el >= end) { stopBreath(); $("brPhase").textContent = "✓ Terminado"; return; }
    const st = [...steps].reverse().find((x) => el >= x.t);
    if (!st) { $("brPhase").textContent = "Prepárate…"; LN.raf = requestAnimationFrame(frame); return; }
    const f = Math.min(1, (el - st.t) / st.secs), key = st.t;
    if (key !== prevKey) { from = parseFloat(($("brCircle").style.transform.match(/[\d.]+/) || [0.45])[0]); prevKey = key; }
    const idx = st.ph;
    const ins = b.phases.filter(([l]) => l.startsWith("Inhala")).length, outs = b.phases.filter(([l]) => l.startsWith("«f»")).length;
    const target = st.label.startsWith("Inhala") ? (ins > 1 ? 0.45 + 0.55 * (idx + 1) / ins : 1)
      : st.label.startsWith("Sostén") ? from
      : st.label.startsWith("«f»") ? 1 - 0.55 * (idx - ins + 1) / outs : 0.45;
    setCircle(from + (target - from) * f);
    $("brPhase").textContent = `${st.label}`;
    $("brCount").textContent = `${Math.ceil(st.secs - (el - st.t))} · vez ${st.cycle + 1} de ${b.cycles}`;
    LN.raf = requestAnimationFrame(frame);
  };
  LN.raf = requestAnimationFrame(frame);
}

// ---------------------------------------------------------------- vocal warm-ups with the piano
// deg: semitones from the key (null = a rest, to breathe); dur: in beats; syl: what is sung on each note
const VOCALS = [
  {id: "mmm", name: "«Mmm» bajando (5-4-3-2-1)", deg: [7, 5, 4, 2, 0], dur: [1, 1, 1, 1, 2], syl: ["mmm", "", "", "", ""],
   tip: "Labios juntos y relajados, dientes separados. Siente cosquillas en los labios y la nariz: así la voz se coloca adelante."},
  {id: "brr", name: "Labios «brrr» (1-3-5-3-1)", deg: [0, 4, 7, 4, 0], dur: [1, 1, 1, 1, 2], syl: ["brrr", "", "", "", ""],
   tip: "Haz vibrar los labios (como un motor) mientras cantas. Si no salen, apoya los dedos en las mejillas. Relaja todo y conecta el aire."},
  {id: "mame", name: "«Ma-me-mi-mo-mu» (1-2-3-4-5-4-3-2-1)", deg: [0, 2, 4, 5, 7, 5, 4, 2, 0], dur: [0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 2],
   syl: ["ma", "me", "mi", "mo", "mu", "mo", "mi", "me", "ma"],
   tip: "Vocales puras del español, todas con la boca igual de abierta por dentro. La «m» ayuda a que la voz esté adelante."},
  {id: "ya", name: "Arpegio «ya» (1-3-5-8-5-3-1)", deg: [0, 4, 7, 12, 7, 4, 0], dur: [0.5, 0.5, 0.5, 1.5, 0.5, 0.5, 2], syl: ["ya", "", "", "", "", "", ""],
   tip: "Una sola «a» ligada en todo el arpegio. En la nota de arriba no subas la barbilla: piensa la nota aguda «hacia adentro» y con más aire."},
  {id: "nu", name: "Escala «nu» (1 al 8 y de vuelta)", deg: [0, 2, 4, 5, 7, 9, 11, 12, 11, 9, 7, 5, 4, 2, 0],
   dur: [0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 1, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 2], syl: ["nu", "", "", "", "", "", "", "", "", "", "", "", "", "", ""],
   tip: "Legato: que no se note el paso de una nota a otra. Si te quedas sin aire, el ejercicio está muy lento: sube la velocidad."},
  {id: "ja", name: "Corto «ja» (1-3-5-3-1, staccato)", deg: [0, 4, 7, 4, 0], dur: [0.5, 0.5, 0.5, 0.5, 1], syl: ["ja", "ja", "ja", "ja", "ja"], staccato: true,
   tip: "Cada «ja» es un pequeño golpe de aire desde la cintura (como una risa). La garganta no empuja: trabaja el abdomen."},
  {id: "vow", name: "Vocales en una nota (mi-me-ma-mo-mu)", deg: [0, 0, 0, 0, 0], dur: [1, 1, 1, 1, 2], syl: ["mi", "me", "ma", "mo", "mu"],
   tip: "La nota no cambia: solo cambia la vocal. Que el sonido siga igual de redondo y afinado en las cinco."},
  {id: "lu", name: "Salto de octava «lu» (1-8-1)", deg: [0, 12, 12, 0], dur: [1, 1.5, 0.5, 2], syl: ["lu", "", "", ""],
   tip: "Prepara el salto con aire, no con fuerza en el cuello. La nota de arriba suave y la de abajo sin caerse."},
  {id: "taka", name: "Agilidad «ta-ka» (1-2-3-4-5-4-3-2-1)", deg: [0, 2, 4, 5, 7, 5, 4, 2, 0], dur: [0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 1],
   syl: ["ta", "ka", "ta", "ka", "ta", "ka", "ta", "ka", "ta"],
   tip: "Lengua suelta y punta de la lengua activa. Las consonantes cortas y la vocal limpia aunque vaya rápido."},
  {id: "bana", name: "Agilidad «ba-na» (1-3-5-3-1-3-5-3-1)", deg: [0, 4, 7, 4, 0, 4, 7, 4, 0], dur: [0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 1],
   syl: ["ba", "na", "ba", "na", "ba", "na", "ba", "na", "ba"],
   tip: "Labios y lengua rápidos, mandíbula quieta. Si se ensucia, más lento."},
  {id: "dame", name: "Escala «da-me-ni-po-tu-la-be-da»", deg: [0, 2, 4, 5, 7, 9, 11, 12], dur: [0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 1.5],
   syl: ["da", "me", "ni", "po", "tu", "la", "be", "da"],
   tip: "Una consonante y una vocal distinta en cada nota: todas claras, sin perder la línea de la escala."},
  {id: "rep", name: "Notas repetidas sin bajar (5-5-5-5 3-3-3-3 1)", deg: [7, 7, 7, 7, 4, 4, 4, 4, 0], dur: [0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 2],
   syl: ["lu", "lu", "lu", "lu", "lu", "lu", "lu", "lu", "lu"],
   tip: "Cada nota repetida con la misma energía: piensa cada una un poquito más alta. La 3.ª, alta; nunca «caída»."},
  {id: "mnl", name: "Consonantes «ma-na-la» (1-1-1 3-3-3 5-5-5 1)", deg: [0, 0, 0, 4, 4, 4, 7, 7, 7, 0], dur: [0.5, 0.5, 1, 0.5, 0.5, 1, 0.5, 0.5, 1, 2],
   syl: ["ma", "na", "la", "ma", "na", "la", "ma", "na", "la", "mmm"],
   tip: "La m, la n y la l con sonido (se pueden sostener): dales su tiempo antes de la vocal, todos juntos."},
  {id: "bon", name: "Diafragma «bon» (5-5-5-5 3-3-3-3 1)", deg: [7, 7, 7, 7, 4, 4, 4, 4, 0], dur: [0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 1],
   syl: ["bon", "bon", "bon", "bon", "bon", "bon", "bon", "bon", "bon"], staccato: true,
   tip: "Pon una mano en la cintura: en cada «bon» siente un pequeño rebote del abdomen. La garganta no hace nada; el aire empuja desde abajo."},
  {id: "blablo", name: "Mandíbula suelta «bla-ble-blo» (1-2-3-2-1)", deg: [0, 2, 4, 2, 0], dur: [1, 1, 1, 1, 2], syl: ["bla", "ble", "blo", "ble", "bla"],
   tip: "Deja caer la mandíbula en cada vocal, como si pesara. La «l» con la punta de la lengua, sin mover la mandíbula para hacerla."},
  {id: "danu", name: "«Da-bi du-bi» (1-2-3-4-5-4-3-2-1)", deg: [0, 2, 4, 5, 7, 5, 4, 2, 0], dur: [0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 2],
   syl: ["da", "bi", "du", "bi", "da", "bi", "du", "bi", "da"],
   tip: "Labios y lengua ligeros; la vocal siempre adelante, aunque cambie de «a» a «i» a «u»."},
  {id: "iuia", name: "Vocales unidas «i-u-i-o-i-a» (en una nota y en 1-3-5)", deg: [0, 0, 0, 4, 4, 4, 7, 7, 7, 0], dur: [0.5, 0.5, 1, 0.5, 0.5, 1, 0.5, 0.5, 1, 2],
   syl: ["i", "u", "a", "i", "o", "a", "i", "u", "a", "a"],
   tip: "Cambia de vocal sin cambiar el sonido: la «i» no se pone chillona ni la «u» se oscurece de más. Todas en el mismo lugar, adelante."},
  {id: "mumi", name: "«Mu-mi» oscura y clara (1-2-1-2-3-2-1)", deg: [0, 2, 0, 2, 4, 2, 0], dur: [1, 1, 1, 1, 1, 1, 2], syl: ["mu", "mi", "mu", "mi", "mu", "mi", "mu"],
   tip: "La «u» redonda y la «i» con el mismo espacio dentro de la boca: que la «i» se parezca un poco a la «u»."},
  {id: "lameo", name: "De agudo a grave «la-me-o» (5-4-3-2-1, bajando)", deg: [7, 5, 4, 2, 0], dur: [1, 1, 1, 1, 2], syl: ["la", "me", "o", "me", "o"], dir: "down",
   tip: "Empieza en una nota aguda cómoda y deja que la voz «baje» ligera, sin cambiar de color al pasar a las notas graves. Que no se note el cambio."},
  {id: "octdown", name: "Octava bajando «u» (8-5-3-1)", deg: [12, 7, 4, 0], dur: [1, 1, 1, 2], syl: ["u", "", "", ""], dir: "down",
   tip: "La nota de arriba suave y en la cabeza; baja sin empujar, llevando ese mismo sonido a las notas graves."},
  {id: "ming", name: "Resonancia «ming-ga» (1-3-5-3-1)", deg: [0, 4, 7, 4, 0], dur: [1, 0.5, 0.5, 1, 2], syl: ["ming", "ga", "ming", "ga", "a"],
   tip: "En «ng» la boca abierta como en una «a», pero el sonido por la nariz: siente cómo vibra la cara. Al abrir a la «a», que esa vibración se quede."},
  {id: "dingdong", name: "Campanas «ding-dong» (5-3-1)", deg: [7, 4, 0, 7, 4, 0], dur: [1, 1, 2, 1, 1, 2], syl: ["ding", "dong", "dong", "ding", "dong", "dong"],
   tip: "Como campanas que resuenan: cada nota sigue sonando por la «ng». Escucha la nota siguiente por dentro antes de cantarla."},
  {id: "tiptop", name: "Labios «pi-po-pa» (1-1-1 2-2-2 3-3-3 1)", deg: [0, 0, 0, 2, 2, 2, 4, 4, 4, 0], dur: [0.5, 0.5, 1, 0.5, 0.5, 1, 0.5, 0.5, 1, 2],
   syl: ["pi", "po", "pa", "pi", "po", "pa", "pi", "po", "pa", "pa"],
   tip: "Labios sueltos y activos, sin apretarlos ni estirarlos. Exagera un poco la forma de la «o» (redonda) y de la «a» (abierta)."},
  {id: "messa", name: "Crecer y bajar en una nota «a» (p < f > p)", deg: [0, 4, 7], dur: [4, 4, 4], syl: ["a", "o", "u"],
   tip: "En cada nota: empieza suave, crece poco a poco hasta fuerte y vuelve a suave, sin que la nota suba ni baje. Lo difícil es el final suave: no le quites el apoyo."},
  {id: "triple", name: "Tresillos «ma-la-ga» (1-2-3 4-5-4 3-2-1)", deg: [0, 2, 4, 5, 7, 5, 4, 2, 0, 0], dur: [1/3, 1/3, 1/3, 1/3, 1/3, 1/3, 1/3, 1/3, 1/3, 1],
   syl: ["ma", "la", "ga", "ma", "la", "ga", "ma", "la", "ga", "ma"],
   tip: "Acentúa un poco la primera de cada grupo de tres. Ligero, como rodando."},
  {id: "fifth", name: "Oído: quinta y tercera «no» (1-5-3-1)", deg: [0, 7, 4, 0], dur: [1, 1, 1, 2], syl: ["no", "no", "no", "no"],
   tip: "Antes de cada nota, escúchala por dentro. La quinta, limpia y estable; la tercera, un poco alta. Prueba el piano en «solo el primer acorde»."},
  {id: "synco", name: "Ritmo sincopado «na» (en una nota)", deg: [0, 0, 0, null, 0, 0, 0, 0], dur: [0.5, 1, 0.5, 0.5, 0.5, 0.5, 0.5, 2],
   syl: ["na", "na", "na", "", "na", "na", "na", "na"],
   tip: "Marca el pulso con el pie y canta las notas cortas y precisas. La nota que cae entre tiempos (síncopa) se acentúa un poco."},
  {id: "breath", name: "Respirar en la frase «na – na – na»", deg: [7, null, 7, null, 7, null, 0], dur: [1.5, 0.5, 1.5, 0.5, 1.5, 0.5, 2],
   syl: ["na", "(aire)", "na", "(aire)", "na", "(aire)", "na"],
   tip: "Corta la nota, toma aire rápido en el silencio y vuelve a la misma nota sin golpearla, al mismo volumen."},
];
const RANGES = {   // comfortable for warming up (sounding notes; men sing an octave below the treble clef)
  soprano: {name: "Soprano", lo: 60, hi: 77}, alto: {name: "Contralto", lo: 55, hi: 72},
  tenor: {name: "Tenor", lo: 48, hi: 67}, baritone: {name: "Barítono", lo: 45, hi: 64}, bass: {name: "Bajo", lo: 41, hi: 60},
};
const VC = {};
function voiceOptions() { return Object.entries(RANGES).map(([k, r]) => `<option value="${k}">${r.name}</option>`).join(""); }
function rememberVoice(sel) {
  try { const v = localStorage.getItem("coralis.voice"); if (v && RANGES[v]) sel.value = v; } catch (e) { /* default */ }
  sel.addEventListener("change", () => { try { localStorage.setItem("coralis.voice", sel.value); } catch (e) { /* convenience */ } });
}
function vocalWidget(preset = {}) {
  $("lnWidget").innerHTML = `<div class="ln-widget">
    <div class="row" style="gap:10px;flex-wrap:wrap">
      <label>Ejercicio <select id="vcEx">${VOCALS.map((v, i) => `<option value="${i}">${esc(v.name)}</option>`).join("")}</select></label>
      <label>Voz <select id="vcVoice">${voiceOptions()}</select></label></div>
    <div class="row" style="gap:10px;flex-wrap:wrap;margin-top:8px">
      <label>Desde <select id="vcFrom"></select></label><label>hasta <select id="vcTo"></select></label>
      <label>Velocidad ♩ = <input type="number" id="vcBpm" min="40" max="160" value="96" style="width:64px"></label>
      <label>Piano <select id="vcPiano"><option value="melody">toca la melodía</option><option value="chord">solo el acorde (a capella)</option>
        <option value="check">a capella, y comprueba la última nota</option>
        <option value="first">solo el primer acorde (el siguiente tono, de oído)</option></select></label></div>
    <div class="row" style="gap:10px;flex-wrap:wrap;margin-top:8px">
      <label>Dirección <select id="vcDir"><option value="up">subir</option><option value="down">bajar</option><option value="updown">subir y volver a bajar</option></select></label>
      <label><input type="checkbox" id="vcAccel"> Acelerar en cada repetición (hasta el doble)</label></div>
    <p class="hint" id="vcTip" style="margin:10px 0"></p>
    <div class="ln-svg" id="vcStaff"></div>
    <div class="vc-now"><div id="vcKey">—</div><div id="vcSyl"></div></div>
    <div class="row" style="justify-content:center"><button class="btn primary" id="vcGo">▶ Empezar</button></div></div>`;
  rememberVoice($("vcVoice"));
  if (preset.ex) $("vcEx").value = Math.max(0, VOCALS.findIndex((v) => v.id === preset.ex));
  if (preset.piano) $("vcPiano").value = preset.piano;
  if (preset.accel) { $("vcAccel").checked = true; $("vcBpm").value = 60; }
  const setDir = () => { $("vcDir").value = VOCALS[+$("vcEx").value].dir || "up"; };
  setDir();
  const fillRange = () => {
    const r = RANGES[$("vcVoice").value], ex = VOCALS[+$("vcEx").value];
    const top = Math.max(...ex.deg.filter((d) => d != null)), lo = r.lo, hi = r.hi - top;
    const opts = [];
    for (let m = lo; m <= hi; m++) opts.push(`<option value="${m}">${noteName(m)}</option>`);
    $("vcFrom").innerHTML = opts.join(""); $("vcTo").innerHTML = opts.join("");
    $("vcFrom").value = lo; $("vcTo").value = Math.min(hi, lo + 7);
  };
  const showEx = async () => {
    const ex = VOCALS[+$("vcEx").value];
    $("vcTip").textContent = ex.tip;
    const names = {0: "c'", 2: "d'", 4: "e'", 5: "f'", 7: "g'", 9: "a'", 11: "b'", 12: "c''"};
    const figs = {0.5: "8", 1: "4", 1.5: "4.", 2: "2", 3: "2."};
    const note = (i, fig) => ex.deg[i] == null ? `r${fig}` : `${names[ex.deg[i]]}${fig}${ex.syl[i] ? "_" + ex.syl[i] : ""}`;
    const third = (d) => Math.abs(d - 1 / 3) < 1e-6, parts = [];
    for (let i = 0; i < ex.deg.length; i++) {
      if (third(ex.dur[i]) && third(ex.dur[i + 1] || 0) && third(ex.dur[i + 2] || 0)) {   // a triplet of eighths
        parts.push(`trip{${note(i, "8")} ${note(i + 1, "8")} ${note(i + 2, "8")}}`); i += 2;
      } else parts.push(note(i, {4: "1", 3: "2.", 2: "2", 1.5: "4.", 1: "4", 0.5: "8"}[ex.dur[i]] || "4"));
    }
    const tiny = parts.join(" ");
    const r = await exampleData({tiny, scale: 40});
    $("vcStaff").innerHTML = r && r.ok ? r.svg + `<p class="hint" style="text-align:center;margin:0">Escrito en do; el piano lo sube medio tono cada vez.</p>` : "";
    $("vcSyl").innerHTML = ex.syl.map((s, i) => `<span id="vcS${i}">${esc(s || "·")}</span>`).join(" ");
    fillRange();
  };
  $("vcEx").onchange = () => { stopVocal(); setDir(); showEx(); };
  $("vcVoice").addEventListener("change", () => { stopVocal(); fillRange(); });
  $("vcGo").onclick = () => LN.raf ? stopVocal() : startVocal();
  showEx();
}
function stopVocal() {
  laStop();
  if ($("vcGo")) { $("vcGo").textContent = "▶ Empezar"; $("vcKey").textContent = "—"; }
  document.querySelectorAll(".vc-now span.on").forEach((e) => e.classList.remove("on"));
}
async function startVocal() {
  laStop();
  const ex = VOCALS[+$("vcEx").value];
  let a = +$("vcFrom").value, b = +$("vcTo").value; if (b < a) [a, b] = [b, a];
  const keys = [], dir = $("vcDir").value;
  if (dir === "down") for (let m = b; m >= a; m--) keys.push(m);
  else { for (let m = a; m <= b; m++) keys.push(m); if (dir === "updown") for (let m = b - 1; m >= a; m--) keys.push(m); }
  const midis = new Set();
  keys.forEach((k) => { ex.deg.forEach((d) => { if (d != null) midis.add(k + d); }); [0, 4, 7, 12].forEach((d) => midis.add(chordNote(k, d))); });
  $("vcKey").textContent = "Preparando el piano…";
  await laReady([...midis]);
  const bpm0 = Math.max(40, Math.min(160, +$("vcBpm").value || 96)), bpm1 = Math.min(200, bpm0 * 2);
  const piano = $("vcPiano").value, accel = $("vcAccel").checked;
  const lastDeg = [...ex.deg].reverse().find((d) => d != null);
  const plan = [];
  let t = LA.ctx.currentTime + 0.3;
  keys.forEach((k, r) => {
    const bpm = accel && keys.length > 1 ? bpm0 + (bpm1 - bpm0) * r / (keys.length - 1) : bpm0, beat = 60 / bpm;
    // the chord of the key (1 beat), a beat to breathe, the exercise, a beat of rest. «First chord only»:
    // after the first time a click marks the time and the singers find the new key by ear
    if (piano !== "first" || r === 0) [0, 4, 7, 12].forEach((d) => laNote(chordNote(k, d), t, beat * 1.1, 0.45));
    else { laClick(t, true); laClick(t + beat, false); }
    plan.push({t, key: k, i: -1, bpm, r});
    t += 2 * beat;
    ex.deg.forEach((d, i) => {
      const len = ex.dur[i] * beat;
      if (d != null && (piano === "melody" || (piano === "first" && r === 0))) laNote(k + d, t, ex.staccato ? len * 0.45 : len * 0.95, 0.7);
      plan.push({t, key: k, i, bpm, r});
      t += len;
    });
    if (piano === "check") { laNote(k + lastDeg, t, beat * 1.4, 0.75); plan.push({t, key: k, i: -2, bpm, r}); t += 1.5 * beat; }
    t += beat;
  });
  const end = t;
  $("vcGo").textContent = "⏹ Parar";
  const gen = LN.gen, frame = () => {
    if (gen !== LN.gen) return;   // another exercise took over
    const now = LA.ctx.currentTime;
    if (now >= end) { stopVocal(); $("vcKey").textContent = "✓ Terminado"; return; }
    const p = [...plan].reverse().find((x) => now >= x.t) || plan[0];
    const hidden = piano === "first" && p.r > 0, lower = hidden && keys[p.r] < keys[p.r - 1];
    $("vcKey").textContent = `Tono: ${hidden ? "medio tono " + (lower ? "más abajo" : "más arriba") + " (de oído)" : noteName(p.key, false)}${p.i === -1 ? " · respira…" : p.i === -2 ? " · ¿suena igual que tu última nota?" : ""}` +
      (accel ? ` · ♩ = ${Math.round(p.bpm)}` : "");
    document.querySelectorAll(".vc-now span").forEach((e, j) => e.classList.toggle("on", j === p.i));
    LN.raf = requestAnimationFrame(frame);
  };
  LN.raf = requestAnimationFrame(frame);
}
function chordNote(k, d) {   // the accompaniment chord: not too low for the men's keys
  const root = k < 52 ? k + 12 : k;
  return root + d;
}

// ---------------------------------------------------------------- blend: the chord, one voice at a time
const CHORD_VOICES = [["Bajo", 0], ["Barítono", 7], ["Contralto", 16], ["Soprano", 24]];   // from the bass: root, 5th, 10th, 2 octaves
function chordWidget() {
  $("lnWidget").innerHTML = `<div class="ln-widget"><div class="row" style="gap:10px;flex-wrap:wrap">
    <label>Tonalidad <select id="chKey">${NOTE_ES.map((n, i) => `<option value="${i}">${n} mayor</option>`).join("")}</select></label>
    <label>Vocal <select id="chVow"><option>u</option><option>o</option><option selected>a</option><option>e</option><option>i</option></select></label>
    <label>Cada voz entra cada <select id="chEvery"><option value="3">3</option><option value="4" selected>4</option><option value="6">6</option></select> segundos</label>
    <label>Piano <select id="chPiano"><option value="each">da la nota de cada voz</option><option value="first">solo la primera (las demás, de oído)</option></select></label>
    <button class="btn primary" id="chGo">▶ Empezar</button></div>
    <div class="ch-voices" id="chVoices"></div><p class="hint" id="chMsg" style="text-align:center"></p></div>`;
  $("chKey").value = 7;   // sol mayor: a comfortable chord for everyone
  const render = (on = -1) => {
    const k = +$("chKey").value, bass = 40 + ((k - 4 + 12) % 12);
    $("chVoices").innerHTML = CHORD_VOICES.slice().reverse().map(([name, d], j) => {
      const idx = CHORD_VOICES.length - 1 - j;
      return `<div class="${idx <= on ? "on" : ""}"><b>${name}</b><span>${noteName(bass + d)}</span><span class="hint">«${esc($("chVow").value)}»</span></div>`;
    }).join("");
  };
  for (const id of ["chKey", "chVow"]) $(id).onchange = () => { laStop(); $("chGo").textContent = "▶ Empezar"; render(); };
  $("chGo").onclick = async () => {
    if (LN.raf) { laStop(); $("chGo").textContent = "▶ Empezar"; render(); $("chMsg").textContent = ""; return; }
    const k = +$("chKey").value, bass = 40 + ((k - 4 + 12) % 12), every = +$("chEvery").value, each = $("chPiano").value === "each";
    const notes = CHORD_VOICES.map(([, d]) => bass + d);
    await laReady(notes);
    const t0 = LA.ctx.currentTime + 0.3, end = t0 + every * 4 + 4;
    notes.forEach((m, i) => { if (each || i === 0) laNote(m, t0 + i * every, 1.6, 0.7); });
    laNote(notes[0], end - 3, 2.5, 0.4); notes.slice(1).forEach((m) => laNote(m, end - 3, 2.5, 0.35));   // the full chord, to check
    $("chGo").textContent = "⏹ Parar";
    const gen = LN.gen, frame = () => {
    if (gen !== LN.gen) return;   // another exercise took over
      const el = LA.ctx.currentTime - t0;
      if (LA.ctx.currentTime >= end) { laStop(); $("chGo").textContent = "▶ Empezar"; $("chMsg").textContent = "✓ ¿Sonaba como el acorde del piano?"; return; }
      const on = Math.min(3, Math.floor(el / every));
      render(el < 0 ? -1 : on);
      $("chMsg").textContent = el >= every * 4 ? "El piano toca el acorde: compara" : el < 0 ? "" : `Entra: ${CHORD_VOICES[on][0]} · misma vocal, mismo volumen`;
      LN.raf = requestAnimationFrame(frame);
    };
    LN.raf = requestAnimationFrame(frame);
  };
  render();
}

// ---------------------------------------------------------------- breath control: hold the note (with a record)
function holdWidget() {
  $("lnWidget").innerHTML = `<div class="ln-widget"><div class="row" style="gap:10px;flex-wrap:wrap">
    <label>Voz <select id="hdVoice">${voiceOptions()}</select></label>
    <label>Vocal <select id="hdVow"><option>a</option><option>o</option><option>u</option><option>e</option><option>i</option><option value="sss">«sss» (sin nota)</option></select></label>
    <label><input type="checkbox" id="hdTick"> Tic cada segundo</label></div>
    <div class="hd-count" id="hdCount">0</div>
    <p style="text-align:center" id="hdMsg">Pulsa «Empezar»: el piano da la nota, respiras, y la sostienes.</p>
    <div class="row" style="justify-content:center;gap:10px"><button class="btn primary" id="hdGo">▶ Empezar</button>
      <button class="btn" id="hdStop" disabled>Se me acabó el aire (espacio)</button></div>
    <p class="hint" style="text-align:center" id="hdBest"></p></div>`;
  rememberVoice($("hdVoice"));
  const best = () => { try { return JSON.parse(localStorage.getItem("coralis.hold") || "{}"); } catch (e) { return {}; } };
  const showBest = () => { const b = best()[$("hdVoice").value + $("hdVow").value]; $("hdBest").textContent = b ? `Tu récord: ${b.toFixed(1)} segundos` : ""; };
  $("hdVoice").addEventListener("change", showBest); $("hdVow").onchange = showBest;
  let start = null;
  const finish = () => {
    if (start == null) return;
    const secs = LA.ctx.currentTime - start; start = null; laStop();
    const key = $("hdVoice").value + $("hdVow").value, all = best(), prev = all[key] || 0;
    if (secs > prev) { all[key] = secs; try { localStorage.setItem("coralis.hold", JSON.stringify(all)); } catch (e) { /* convenience */ } }
    $("hdCount").textContent = secs.toFixed(1);
    $("hdMsg").innerHTML = secs > prev ? `<b style="color:var(--accent)">¡Nuevo récord! ${secs.toFixed(1)} s</b>` : `${secs.toFixed(1)} segundos. Respira tranquilo y vuelve a intentar.`;
    $("hdGo").disabled = false; $("hdStop").disabled = true; showBest();
  };
  $("hdStop").onclick = finish;
  $("lnWidget").addEventListener("keydown", (e) => { if (e.code === "Space" && start != null) { e.preventDefault(); finish(); } });
  document.addEventListener("keydown", function onKey(e) {
    if (!$("hdStop")) { document.removeEventListener("keydown", onKey); return; }
    if (e.code === "Space" && start != null) { e.preventDefault(); finish(); }
  });
  $("hdGo").onclick = async () => {
    const r = RANGES[$("hdVoice").value], note = Math.round((r.lo + r.hi) / 2) - 2, sss = $("hdVow").value === "sss";
    await laReady([note]); laStop();
    const t0 = LA.ctx.currentTime + 0.2;
    if (!sss) laNote(note, t0, 1.5, 0.7);
    $("hdGo").disabled = true; $("hdStop").disabled = false;
    $("hdMsg").textContent = sss ? "Respira… y suelta el aire en «sss»" : `Escucha la nota (${noteName(note)}), respira… y sostenla en «${$("hdVow").value}»`;
    const go = t0 + (sss ? 2.5 : 3);
    if ($("hdTick").checked) for (let k = 0; k < 120; k++) laClick(go + k, k % 5 === 0);
    const gen = LN.gen, frame = () => {
    if (gen !== LN.gen) return;   // another exercise took over
      const now = LA.ctx.currentTime;
      if (start == null && now >= go) { start = go; $("hdMsg").textContent = "¡Ahora! Sostén parejo…"; }
      if (start != null) $("hdCount").textContent = (now - start).toFixed(1);
      if ($("hdStop") && !$("hdStop").disabled) LN.raf = requestAnimationFrame(frame);
    };
    LN.raf = requestAnimationFrame(frame);
  };
  showBest();
}

const ROUTINE = [
  ["Calentar el cuerpo", 2, "Calentar el cuerpo"], ["Respiración", 2, "Respiración"], ["El diafragma", 1, "El diafragma"],
  ["Vocalizar (empieza en el medio de la voz)", 3, "Vocalizar con el piano"], ["Vocales", 1, "Vocales: formarlas y unirlas"],
  ["De grave a agudo", 2, "De grave a agudo sin quiebres"], ["Oído: afinación", 2, "Afinación y oído"],
  ["Para terminar: un acorde o un canon conocido en una sílaba", 1, "Empaste: el acorde voz por voz"],
];
function routineWidget() {
  const total = ROUTINE.reduce((a, r) => a + r[1], 0);
  $("lnWidget").innerHTML = `<div class="ln-widget"><ol class="rt-list">${ROUTINE.map(([name, min, lesson]) =>
    `<li><span>${esc(name)}</span><span class="hint">${min} min</span>
      <button class="btn" onclick="openLesson('vocal', ${JSON.stringify(lesson).replace(/"/g, "&quot;")})">Ir ▶</button></li>`).join("")}</ol>
    <p class="hint" style="margin:6px 0 0">Unos ${total} minutos. Si ensayan todos juntos, las voces graves descansan en los tonos más agudos y las agudas
      en los más graves.</p></div>`;
}
function openLesson(tab, title) {
  laStop(); LN.tab = tab; renderLearnTabs();
  showLesson(Math.max(0, LESSONS[tab].items.findIndex((it) => it.title === title)));
}
const WIDGETS = {quiz: quizWidget, pattern: patternWidget, pitch: pitchWidget, breath: breathWidget, vocal: vocalWidget,
                 chord: chordWidget, hold: holdWidget, checklist: checklistWidget, routine: routineWidget};
