// Copia a interface buildada (apps/web/dist) pra dentro do app de bandeja.
// Assim a janela abre instantaneamente, sem depender do servidor estar no ar.
const fs = require('fs')
const path = require('path')

const src = path.join(__dirname, '..', 'web', 'dist')
const dst = path.join(__dirname, 'build', 'web')

if (!fs.existsSync(src)) {
  console.error('apps/web/dist não existe — rode "npm run build" em apps/web primeiro.')
  process.exit(1)
}
fs.rmSync(dst, { recursive: true, force: true })
fs.cpSync(src, dst, { recursive: true })
console.log(`interface copiada: ${src} -> ${dst}`)

// Grava onde está o projeto. O app instalado fica em %LOCALAPPDATA%\Programs e
// não tem como adivinhar o repositório — é daqui que ele lê o token e é isto que
// ele usa pra subir o servidor. Sem este arquivo o exe vira só uma casca.
const raiz = path.resolve(__dirname, '..', '..')
fs.writeFileSync(path.join(__dirname, 'build', 'projeto.json'),
                 JSON.stringify({ raiz }, null, 2))
console.log(`projeto gravado no pacote: ${raiz}`)
