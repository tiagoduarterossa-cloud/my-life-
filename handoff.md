# Handoff da central do quarto

Para a próxima sessão (com o Claude ou com outra pessoa) começar onde esta acabou. Atualiza-o no fim de cada sessão.

Atenção: o repositório é público. Aqui não vão nomes da família, moradas, cidades, PINs nem chaves.

# Objetivo

Uma central pessoal num Samsung Galaxy Tab S7+ preso à parede, a correr em Termux. Serve para organizar a escola (testes, tarefas, horário, estudo), a casa (luzes, alarmes, rotinas) e um assistente por voz ao estilo Jarvis. A parte privada (família, mapa, loja Shopify, segurança) fica só no modo Iron Man, trancada com PIN.

Regra de ouro: **tudo o que a central diz tem de ser verdade e ter fonte**. Se uma fonte falhar, diz "sem dados" e não inventa.

## Estado atual

Funciona e está testado:
- **Ecrã inicial**: tarefas, estudo, horário, tempo, quarto 3D, roupa, despertador, rotinas.
- **Voz**: o trinco "escuta" vem antes do "Jarvis". O trinco fica aberto enquanto o ecrã do Jarvis ou do Iron Man está visível, e mais 20 s depois de cada pedido ou de sair do Iron Man. Há limites de segurança para quando a voz do Android não avisa que acabou de falar, e uma vigia que volta a ligar o microfone se ele ficar desligado.
- **Iron Man**: meteorologia, sistemas, agenda, missões, loja, família, áudio e faixa de notícias.
- **Mapa**: contorno do Natural Earth, Açores e Madeira em caixas, avisos do IPMA (o mar pinta só a costa), vento do Open-Meteo, incêndios, sismos e a casa a vermelho quando falta a luz. Tocar num ponto abre a ficha da pessoa.
- **Ficha de cada familiar**: tempo, avisos do IPMA com texto, incêndios, sismos e notícias da terra (Google Notícias), cada parte com a fonte.
- **PIN**: hash PBKDF2 em pin.json e sessões em cookie HttpOnly. No tablet, o ecrã normal fica livre e o Iron Man pede o PIN. Noutros aparelhos pede-se sempre. Há bloqueio contra quem tenta adivinhar e chaves para a Siri e os sensores.
- **Modo apagão**: liga-se sozinho quando o tablet deixa de carregar. Corta o que gasta bateria e mostra bateria, rádio (radio-browser.info), notícias e conselhos com fonte. Sai pelo botão no topo ou no fundo.
- **O que está a funcionar**: Wi-Fi, router, internet, DNS e 14 serviços testados a partir de casa.
- **Loja Shopify**: lucro real e despesas por voz. Falta ligar a loja no tablet.

Falta configurar no tablet (não é código):
- Ligar o Spotify (definições).
- Ligar a loja (Iron Man > Loja).
- Pedir a chave do fogos.pt e guardá-la em `fogos_token.txt`.
- Dar à Termux:API as autorizações de localização, notificações e "Alterar definições do sistema" (para o brilho).
- Ter um rádio a pilhas em casa, com as frequências FM escritas num papel.

## Ficheiros

- `server.py`: servidor HTTP (só biblioteca padrão), todos os endereços `/api/...`, as regras do PIN e as tarefas em segundo plano.
- `assistente.py`: percebe as frases (`entender`) e responde (`_responder`). A ordem das regras importa. `PRIVADAS` diz o que só responde com PIN.
- `ia.py`: Claude como plano B quando as regras não percebem. Usa a ferramenta `central` e esconde as conversas privadas a quem não tem PIN.
- `familia.py`: familiares, perigos perto da casa deles, mapa, ficha (`detalhe`) e a vigia de 15 em 15 minutos.
- `avisos.py`: IPMA (distritos e ilhas, terra e mar), USGS, fogos.pt (chave), vento, energia e apagões (Termux:API).
- `pin.py`, `radio.py`, `servicos.py`, `loja.py`, `seguranca.py`, `casa.py`, `noticias.py`, `rotinas.py`, `alarmes.py`, `voz.py`, `spotify.py`, `dispositivos.py`.
- `static/index.html`: a interface toda (HTML, CSS e JS sem bibliotecas).
- `static/mapa_pt.js`: contornos do Natural Earth (domínio público).
- `static/quarto.js`: visualizador 3D do quarto.
- `iniciar.sh`, `instalar.sh`, `atualizar.sh`: no Termux, a central está em `~/central`.
- Fora do GitHub (.gitignore): `vida.db`, `pin.json`, `chave_claude.txt`, `spotify_token.json`, `loja_token.json`, `fogos_token.txt`, `radio_cache.json`, `static/quarto/`.

## O que mudou

Nesta sessão (resumo dos commits):
- Família e mapa no Iron Man, loja e segurança passadas para o Iron Man, respostas privadas que não ficam no histórico do chat.
- PIN completo.
- Voz: o trinco "escuta", os resultados provisórios (o Android fecha o microfone sem dar a frase), 150 ms entre sessões de escuta, os 10 s para o pedido a contar depois da resposta, os limites de segurança e a vigia do microfone.
- Um só motor de som. Antes criava-se um AudioContext a cada som, e no Android isso deixava o tablet lento e roubava o áudio ao microfone.
- "Que horas são", "que dia é hoje", "tenho teste de X na sexta", "brilho a 50", "modo apagão", "está tudo a funcionar?", "o WhatsApp está em baixo?".
- Mapa realista, ficha de cada familiar, modo apagão, estado dos serviços.
- Revisão: a frase "gastei X euros" estava estragada (barras a mais na expressão regular) e o servidor passou a responder 500 com uma mensagem clara em vez de cortar a ligação.

## Tentativas falhadas

- **Palavra de ativação com Picovoice**: precisa de email de empresa. Ficou o Web Speech API do Chrome, que só funciona em `http://127.0.0.1` e envia o som para a Google, mesmo com o trinco.
- **Tailscale**: a Play Store não instalava. Ficou adiado.
- **fogos.pt sem chave**: passou a exigir o cabeçalho FOGOS-PT-AUTH, e sem chave dá "sem dados".
- **Cortes de luz da E-REDES para outras casas**: o conjunto de dados aberto (`outages-per-geography`) parece desatualizado e não foi verificado. Não está ligado, para não mostrar dados errados.
- **Frequências FM e endereços de rádio escritos à mão**: não foram confirmados em fonte oficial. Por isso os endereços vêm do radio-browser.info em tempo real e as frequências não estão na central.
- **Um "estado de Portugal" (o WhatsApp em baixo no país todo)**: não existe uma fonte pública fiável. A central só testa a partir de casa.
- **Câmaras escondidas à porta dos avós a registar carros desconhecidos**: recusado (RGPD, via pública). A alternativa é uma campainha com câmara à vista, se os avós quiserem.
- **O ambiente de testes do Claude não tem internet aberta**: tudo foi testado com servidores falsos (IPMA, USGS, fogos, rádio, Open-Meteo, notícias, Claude, Spotify, Shopify, WLED, Shelly) e Playwright. A prova final é sempre no tablet.

## Próximo passo

1. **Usar a central durante uma semana**: registar o estudo, marcar os testes por voz, usar a rotina de dormir. No fim, dizer o que se usou e o que nunca se abriu.
2. No tablet: atualizar (`cd ~/central && ./atualizar.sh`), pôr o PIN, meter a família e testar o "escuta" e o modo apagão ("Jarvis, modo apagão" e o botão de sair).
3. Se alguma parte disser "sem dados" durante mais de um dia, tirar uma foto ao ecrã e ao Termux.
4. Ideias por fazer, por ordem de utilidade: backups automáticos do `vida.db`, relatório semanal do estudo, trabalhos novos do Teams (pelas notificações do Android), ações da bolsa, Tailscale, ligação entre o quarto 3D e a roupa.
5. Pensar em tornar o repositório privado (o código não tem dados pessoais, mas mostra como a central funciona).
