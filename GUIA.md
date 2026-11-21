# Guía de Coralis

Coralis convierte un himno o una partitura coral (PDF o fotos) en un archivo con las 4 voces y la letra,
listo para estudiar: lo puedes escuchar con piano, corregir, imprimir y convertir en audio o en video.

> **Importante:** Coralis puede equivocarse. Lee la partitura con programas de reconocimiento automático y
> aplica reglas para corregir lo que puede, pero notas, ritmos, letra, repeticiones o estrofas pueden salir mal,
> sobre todo en fotos, arreglos poco comunes o letra difícil de leer. Coralis marca los compases dudosos para
> que los revises. **Compara siempre el resultado con la partitura impresa: la decisión final la tienes tú.**

Contenido:

1. [Instalar y abrir](#1-instalar-y-abrir)
2. [Convertir un himno](#2-convertir-un-himno)
3. [Los himnos convertidos](#3-los-himnos-convertidos)
4. [Escuchar y ensayar](#4-escuchar-y-ensayar)
5. [Guardar audio, video, MIDI, PDF y partituras](#5-guardar-audio-video-midi-pdf-y-partituras)
6. [Editar: corregir todo, compás por compás](#6-editar-corregir-todo-compás-por-compás)
7. [Signos, letra como texto y nombres de las voces](#7-signos-letra-como-texto-y-nombres-de-las-voces)
8. [Atajos de teclado](#8-atajos-de-teclado)
9. [Dónde se guarda todo](#9-dónde-se-guarda-todo)
10. [Consejos y límites](#10-consejos-y-límites)

---

## 1. Instalar y abrir

- **Mac con chip de Apple (M1 o posterior):** descarga el `.dmg` de la última versión en
  [Releases](https://github.com/OrlandoFloresC/Coralis/releases), ábrelo y arrastra Coralis a Aplicaciones.
  La primera vez macOS dirá que no puede comprobar el desarrollador (la app no está firmada):
  **Ajustes del Sistema → Privacidad y seguridad → «Abrir igualmente»**. Solo una vez.
- **Windows 10 u 11 (64 bits):** descarga `Coralis-…-Windows.exe` y ábrelo para instalar. Si aparece
  «Windows protegió su PC», pulsa **Más información → Ejecutar de todos modos**. Solo una vez.

La primera vez que se abre, Coralis descarga sus lectores de partituras (unos 400 MB) y muestra
«Preparando Coralis» con una barra. Puede tardar de 5 a 20 minutos; después ya no.

Cuando hay una versión nueva, Coralis lo avisa al abrirse y ofrece descargarla.

## 2. Convertir un himno

En la pantalla de inicio, en **«La partitura»**:

1. **Arrastra la partitura** al recuadro (o haz clic para elegirla): un PDF, o fotos de una o varias páginas.
   Si son fotos, elígelas todas juntas; se leen en orden alfabético del nombre.
2. **Nombre del himno** (opcional): si lo dejas vacío, se toma el texto más grande de la primera página.
3. **Letra** (opcional, pero mejora mucho la letra): un archivo `.txt` con las estrofas, una por párrafo,
   separadas por una línea en blanco. Los números de estrofa son opcionales:

   ```
   1. Sublime gracia del Señor,
   de muerte me libró.

   2. Mi corazón enterneció,
   mis dudas disipó.
   ```

   Coralis separa las sílabas solo, las coloca en las notas guiándose por lo que leyó y une las sinalefas.
4. Pulsa **Convertir**. Tarda unos 2-3 minutos por página. Al terminar dice «¡Listo!».

Consejos para fotos: buena luz, la hoja derecha y completa, sin sombras. Si se transparenta la página de
atrás, Coralis intenta limpiarla.

## 3. Los himnos convertidos

A la derecha (o abajo en una ventana pequeña) está la lista **«Himnos convertidos»**. Cada himno dice
cuántos compases quedaron dudosos y tiene tres botones:

- **▶ Escuchar:** lo toca con piano y metrónomo, con la partitura a la vista, y desde ahí guardas audio,
  video, PDF, partitura o MIDI (ver [4](#4-escuchar-y-ensayar) y [5](#5-guardar-audio-video-midi-pdf-y-partituras)).
- **✎ Editar:** corrige notas, ritmo, letra, compases y signos viendo la imagen original
  (ver [6](#6-editar-corregir-todo-compás-por-compás)).
- **Abrir ▾:** un menú con
  - **Para practicar:** el archivo de 4 voces (MusicXML) en MuseScore o tu programa de partituras, con las
    estrofas una tras otra y las repeticiones desplegadas, como para la app de solfeo;
  - **Copia digital:** la versión en 2 pentagramas como el original, con sus repeticiones y signos;
  - **Reporte:** cada compás con su imagen, lo que entendió Coralis y por qué es dudoso;
  - **Carpeta del himno:** donde se guarda todo.

Si guardaste cambios en el editor sin rehacer la partitura, el himno dice «cambios sin rehacer»; se rehace
solo antes de abrirlo, escucharlo o descargar algo.

## 4. Escuchar y ensayar

**▶ Escuchar** toca las 4 voces con un piano de cola. Los controles:

- **▶ Reproducir / ⏸ Pausa / ⏹ Detener.** **Desde el compás:** dónde empieza. También puedes hacer clic en la
  barra de avance o **en cualquier compás de la partitura** para ir ahí.
- **Velocidad:** escribe el número y pulsa Intro, o usa − y +. Se puede cambiar mientras suena; sigue desde
  el mismo punto. En 6/8, 9/8 y 12/8 la velocidad es de la negra con puntillo.
- **Metrónomo** (se enciende y apaga al momento) y **Un compás de entrada** (cuenta antes de empezar).
- **Tono:** − y + suben o bajan todo el himno de medio tono en medio tono. Muestra cuánto y la armadura que
  queda (elige la más sencilla: por ejemplo, Sol + medio tono = La♭). Lo que guardes después sale en ese tono.
- **Repetir del compás … al …:** repite ese tramo sin parar, para ensayarlo. Si cambias los números mientras
  suena, sigue con el tramo nuevo.
- **Ver la partitura:** muestra la partitura completa. El compás que suena lleva un recuadro verde y la nota
  que suena (con su sílaba) se pinta de verde en las 4 voces; la partitura avanza sola.

En **«Voces»**, cada voz tiene:

- **Volumen**, **Destacar** (tu voz fuerte y las demás suaves) y **Sola** (solo esa voz).
- **Lado** (izquierda o derecha, con audífonos). **«🎧 Mi voz a la izquierda, las demás a la derecha»**
  usa la voz destacada; **«Todas al centro»** lo regresa.

Arriba se ve la letra de la voz destacada (o de la soprano) mientras suena.

## 5. Guardar audio, video, MIDI, PDF y partituras

En «Escuchar», el botón **«⬇ Guardar…»** pregunta dos cosas:

- **Qué:** audio (mp3), video con la letra, PDF para imprimir, partitura (MusicXML, para MuseScore o la app de
  solfeo) o MIDI.
- **De quién:**
  - para audio y video: **como suena ahora**, **las 4 voces por igual**, **una voz destacada** (las demás
    suaves), **una voz sola**, o **cada voz** (destacada o sola) en su propio archivo, para mandarle a cada
    cantante el suyo;
  - para PDF, partitura y MIDI: **las 4 voces**, **solo una voz** o **cada voz en su propio archivo**.

Todo sale con el **tono, la velocidad y el metrónomo** que tengas puestos, y se guarda en la carpeta del himno
sin preguntar dónde. Coralis dice el nombre del archivo y ofrece **«Abrir carpeta»**. Los nombres dicen qué son:
«Castillo Fuerte - Alto (2 semitonos más alto).pdf», «Castillo Fuerte - Bajo destacada.mp3».

**El video** se graba en tiempo real (tarda lo que dura el himno; deja la ventana a la vista). Lleva el
título, un compás de cuenta antes de cada estrofa, la letra escrita como en la partitura
(«Sal - va - dor») con lo cantado en color, una rayita por cada tiempo que dura cada sílaba, y el compás
«1 2 3 4» arriba. Después de «Siguiente…» eliges:

- **Nombre del coro o de la iglesia** (va en el título y al pie) y los **colores**.
- **Mostrar el pentagrama** de la voz, con la nota que suena marcada.
- **La letra de las otras voces** cuando cantan otra cosa (por ejemplo, los hombres respondiendo).


## 6. Editar: corregir todo, compás por compás

**✎ Editar** muestra un compás a la vez: arriba la **imagen del compás original**, y debajo las 4 voces,
cada una con su pentagrama, sus notas y su letra. A la derecha están las herramientas de la nota elegida.

**Moverse:** «◀ Anterior / Siguiente ▶», «Ir al compás», y **«◀ dudoso / dudoso ▶»** para saltar entre los
compases que Coralis marcó como dudosos. **Estrofa:** elige qué estrofa de letra ves y escribes.

**Notas** (haz clic en una nota):

- **▲ ▼** sube o baja un grado siguiendo la armadura; **♭ ♮ ♯** pone una alteración.
- **⌒ ligar a la siguiente:** si es la misma nota, una ligadura de prolongación; si es otra nota, una
  ligadura de expresión (las dos notas se cantan en la misma sílaba).
- **Figura:** de redonda a fusa, con puntillo, y **tresillos** (de blanca, negra, corchea y semicorchea).
  Al alargar, la nota ocupa los silencios siguientes (nunca tapa otra nota); al acortar, deja un silencio.
- **◀ mover / mover ▶:** corre la nota sin cambiar su figura, de a semicorchea, corchea de tresillo,
  corchea o negra.
- **🗑 Borrar nota** (queda un silencio), **✂ Dividir** (dos notas iguales) y **③ Tresillo** (tres notas
  iguales: una negra se vuelve tres corcheas de tresillo).
- **Silencios:** haz clic en un silencio y pulsa **«♪ Poner nota aquí»** con la figura elegida. En la
  anacrusa, un silencio que no está impreso se puede quitar.
- **Lecturas (A, B, C…):** en los compases dudosos, las distintas versiones que leyeron los programas, para
  elegir la correcta con un clic.
- **Corregir igual los compases idénticos** (activado): si el himno repite exactamente la misma frase, tu
  corrección se copia a las demás veces.
- **↶ Deshacer / ↷ Rehacer** cualquier cambio.

**Letra:** escribe en la casilla de cada nota, como en MuseScore (ver los atajos en [8](#8-atajos-de-teclado)).
Las notas ligadas se saltan solas. Cada voz muestra lo que canta: en gris, la letra que copia de la melodía;
si escribes ahí, esa voz canta su propia letra (por ejemplo, los hombres respondiendo con otro texto).

**El compás** (panel «Compás N», debajo de las herramientas de la nota; ábrelo con un clic):

- **＋ Compás antes / ＋ Compás después:** agrega un compás de silencios (con la cifra y la armadura del
  anterior), para llenarlo con «Poner nota aquí». Sirve cuando el programa se saltó un compás.
- **🗑 Borrar este compás**, y **↶ Deshacer** el último compás agregado o borrado (vuelve con todo lo que le
  habías corregido). Tus correcciones en otros compases siguen en su lugar.
- **Cifra de compás y armadura:** desde este compás hasta donde el programa leyó otra (o **solo este
  compás**). Con otra armadura, las notas sin alteración propia se ajustan a ella. **«Volver a lo leído»**
  quita tu cambio.
- **⧉ Copiar este compás** y, en otro compás que dure lo mismo, **📋 Pegar las 4 voces** o **pegar solo una**.
- **Signos de este compás:** barras de repetición (𝄆 𝄇), segno, coda, «a la Coda», Fine, salto al final del
  compás (D.S., D.C. …), casilla (1.ª, 2.ª, o «1.-6.») y silencio de varios compases. Los signos del compás se
  ven junto a «Compás N». Se guardan con «Guardar» como todo lo demás, y también se deshacen con ↶.

**Guardar** (igual en el editor, en «𝄋 Signos» y en «Letra como texto»): **«Guardar»** guarda al momento tus
cambios. **«Rehacer partitura»** rehace el archivo para practicar, la copia digital y lo demás con tus cambios
(unos segundos). Si se te olvida, se rehace sola antes de abrir, escuchar o descargar. Agregar o borrar compases y cambiar la cifra o la armadura rehacen la
partitura enseguida.

## 7. Signos, letra como texto y nombres de las voces

En la parte de arriba del editor:

- **𝄋 Signos:** la vista de todo el himno (los signos de un compás también se ponen en el panel «Compás» del
  editor). Todos los compases en miniatura; haz clic en uno para marcar o quitar segno, coda,
  repeticiones (|: :|), casillas (1.ª, 2.ª, o «1.-6.»), D.S./D.C., Fine y silencios de varios compases. Con eso
  Coralis despliega las repeticiones en el archivo para practicar. Lo que los programas no ven (el segno y la
  coda casi nunca) lo marcas aquí.
- **Letra como texto:** toda la letra en párrafos, para corregirla de corrido o pegar la letra correcta. La letra
  que leyó el programa aparece con guiones entre sílabas, como en el himnario («Cas-ti-llo fuer-te»), para que veas
  qué va en cada nota. Corrige solo lo que está mal: lo que no toques se queda en sus notas y sirve de referencia
  para acomodar lo demás. Si dos palabras salen unidas («fuer-te-nues-tro»), pon el espacio («fuer-te nues-tro»).
  La palabra corregida debe tener las mismas sílabas que notas tiene.
  «Volver a la letra leída» deshace ese texto. Se guarda igual que en el editor: «Guardar» y «Rehacer partitura».
- **Nombres de las voces:** cómo se llaman las voces de este himno (por ejemplo, «Cuarteto de hombres»: Primer
  tenor, Segundo tenor, Barítono, Bajo). Se usan en la partitura, al escuchar, en los videos y en los nombres de
  los archivos.

## 8. Atajos de teclado

En el editor, el botón **«⌨ Atajos»** muestra esta misma tabla.

En Windows, **Ctrl** en lugar de ⌘ y **Alt** en lugar de ⌥.

**Notas:**

| Tecla | Qué hace |
|---|---|
| ↑ ↓ | Subir / bajar la nota un grado |
| ⌥← ⌥→ | Mover la nota antes / después |
| ⌥7 ⌥6 ⌥5 ⌥4 ⌥3 | Redonda, blanca, negra, corchea, semicorchea (también mientras escribes la letra) |
| ⌥. | Poner o quitar el puntillo |
| ⌘⌫ | Borrar la nota (queda un silencio) |
| N o Intro (en un silencio) | Poner una nota ahí |
| ⌘Z / ⌘⇧Z | Deshacer / rehacer |

**Letra** (como en MuseScore):

| Tecla | Qué hace |
|---|---|
| `-` | La palabra sigue en la nota siguiente (pone el guion) |
| espacio | Palabra nueva en la nota siguiente |
| `_` | La sílaba se alarga sobre la nota siguiente (melisma, sin guion) |
| ⌥- (o ⌥⌘-) | Sinalefa: dos sílabas en una nota («me‿el») |
| ⌫ en una casilla vacía | Volver a la nota anterior |
| ← → al principio o al final | Nota anterior / siguiente |
| Intro | Compás siguiente |

## Aprende

El botón **«🎓 Aprende»** (arriba, en la pantalla de inicio) abre tres apartados con lecciones cortas. Elige el apartado
arriba y la lección a la izquierda; «◀ Anterior / Siguiente ▶» al final de cada una.

- **Aprende música:** lo básico para leer un himno, con ejemplos que suenan con el piano, y una práctica para
  reconocer notas en clave de sol y de fa.
- **¿Quieres dirigir un coro?:** del gesto básico al ensayo y el concierto. El ejercicio de **patrones** dibuja el
  compás (1, 2, 3, 4 o 6/8) con un punto que sigues con la mano, al ritmo del metrónomo; puedes cambiar la
  articulación (legato, marcato, staccato), el tamaño (p, mf, f), hacer un ritardando o accelerando, y activar
  **«Entradas y cortes al azar»** para practicar dar entradas a cada voz. También: **dar el tono** con el piano,
  dibujos de **cómo acomodar al coro** y una **lista para el concierto** que se queda guardada.
- **Ejercicios de vocalización:** postura, calentamiento del cuerpo y una **rutina de 10-15 minutos** (cada paso
  abre su lección), **respiración guiada**, **sostener la nota** con contador y récord, el **acorde voz por voz**
  para el empaste, y **vocalises con el piano**: eliges el ejercicio, tu voz, desde y hasta qué nota, la dirección
  (subir, bajar o las dos) y la velocidad. El piano puede tocar la melodía, dar solo el acorde (a capella), dar solo
  el primer acorde para que encuentres el siguiente tono de oído, o comprobar la última nota.

## 9. Dónde se guarda todo

Todo va a **Documentos/Coralis**, una carpeta por himno. Ahí están el archivo para practicar
(`<título>.musicxml`), la copia digital, el reporte y todo lo que guardes desde Coralis (mp3, videos, MIDI,
PDF, partituras de una voz). Nada se sube a internet. Al desinstalar Coralis, esa carpeta se conserva.

## 10. Consejos y límites

- **Revisa siempre los compases dudosos** («◀ dudoso / dudoso ▶» en el editor) y compara con la partitura impresa.
- Una **letra en `.txt`** mejora mucho el resultado; la letra impresa entre pentagramas o encima del pentagrama
  casi nunca la leen los programas.
- Los programas no ven el **segno ni la coda**: márcalos en «𝄋 Signos».
- Arreglos difíciles (cuartetos con tarareos, muchos cambios de compás, fotocopias malas) pueden salir con
  muchos errores: corrígelos en el editor o conviértelos desde una imagen más limpia.
- Las notas de adorno, la dinámica (*mf*, *p*) y los textos (*rit.*) no se editan en Coralis.
- **Respeta los derechos de autor** de las partituras que conviertas y compartas.
