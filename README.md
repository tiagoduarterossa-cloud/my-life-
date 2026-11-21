# A minha central

Servidor pessoal que corre num Galaxy Tab S6 Lite antigo. Abre-se no telemóvel ou no PC pelo Wi-Fi de casa.

Tem seis separadores, com um visual ao estilo iOS (claro ou escuro, conforme o tema do aparelho):

- **Início**: o ecrã principal. Relógio grande, o tempo lá fora (Open-Meteo, sem conta nem chave), o que tens agora e a seguir, o próximo teste em contagem decrescente, tarefas urgentes e o tempo de hoje. Tem oito cores à escolha: roxo neon (por defeito), azul, ciano, verde, pôr do sol, vermelho, Aurora (vai mudando de cor sozinho) e Céu (muda com a hora do dia). Ao fim de uns minutos sem mexer entra em modo repouso: relógio gigante, data, temperatura, o que tens agora e o próximo teste. Na roda dentada escolhes o tema, a cidade e as horas em que o ecrã fica sempre ligado; fora dessas horas fica preto, só com o relógio.
- **Tarefas**: tudo o que tens de fazer, com área, prioridade e prazo. As atrasadas aparecem a vermelho.
- **Horário**: calendário do mês com os testes a amarelo e os 3 dias antes de cada teste marcados para estudar (verde se estudaste, vermelho se faltaste). Grelha das aulas igual à da escola, com a aula de agora destacada. E os blocos fixos da semana (aulas, treinos, almoço, estudo).
- **Estudo**: cronómetro de estudo (15, 25, 45 ou 60 min) que, ao terminar, preenche sozinho o diário com a disciplina e os minutos. Lista de testes com contagem dos dias e quanto já estudaste para cada um (conta as sessões do diário dessa disciplina). E o diário de estudo. Cada sessão guarda a disciplina, o que estudaste, como correu e as dúvidas que ficaram. O tempo entra sozinho no separador Tempo, na área Escola.
- **Tempo**: registas quanto tempo deste a cada área e vês o total dos últimos 7 dias.
- **Quarto**: o quarto em 3D, a partir de um scan LiDAR do iPhone. Roda com um dedo, aproxima com dois. Vista 3D, planta vista de cima, teto, e a luz LED na cor do tema. O visualizador é WebGL puro, sem bibliotecas, por isso funciona sem internet.
- **Assistente** (botão redondo em baixo à direita, em qualquer separador): percebe frases em português. "O que tenho amanhã?", "faz-me a mala para Madrid de sexta a domingo" (vê a previsão do tempo e escolhe a tua roupa arrumada), "marca dentista quarta às 15h", "toma nota: ...", "tenho de acabar o trabalho de CN até quinta", "quando é o próximo teste?". No tablet, em `http://127.0.0.1:8080`, também dá para falar: carrega no microfone, ou liga "Ficar à escuta" nas definições e diz **"Rosserini, o que tenho amanhã?"**. Ele responde em voz, num estilo descontraído. A voz, o tom, a velocidade e a palavra de ativação escolhem-se na roda dentada.
- **Roupa**: cola o link da loja e a foto aparece sozinha (se a loja deixar). Todas as peças, onde estão guardadas e se estão arrumadas, para lavar ou emprestadas. Toca na etiqueta para mudar o estado.

Só usa Python, sem bibliotecas extra. Os dados ficam no ficheiro `vida.db`, dentro do tablet. Nada vai para a internet.

## Instalar ou atualizar (o mais fácil)

Depois do `git clone` (ver em baixo), no Termux:

```
cd ~/central && ./instalar.sh
```

Instala tudo, prepara o arranque automático, mete o horário e arranca a central. Pode correr-se outra vez se alguma coisa falhar.

Para ir buscar a versão mais recente e reiniciar: `./atualizar.sh`

## Instalar no tablet (passo a passo, à mão)

### 1. Preparar o tablet

1. Liga o tablet ao carregador e deixa-o ligado.
2. Em **Definições > Assistência do dispositivo > Bateria > Mais definições**, liga **Proteger bateria** (para nos 85%). Como vai estar sempre ligado à corrente, isto evita que a bateria se estrague e inche.
3. Instala a app **F-Droid** a partir de https://f-droid.org (é uma loja de apps livres).
4. No F-Droid instala **Termux** e **Termux:Boot**.
   Não instales o Termux da Play Store, essa versão está desatualizada e dá erros.

### 2. Instalar a central

Abre o Termux e escreve, uma linha de cada vez:

```
pkg update
pkg install python git
git clone https://github.com/tiagoduarterossa-cloud/my-life-.git central
cd central
./iniciar.sh
```

Se o repositório for privado, o GitHub pede utilizador e palavra-passe. Na palavra-passe tens de usar um *token* (GitHub > Settings > Developer settings > Personal access tokens). Pede ajuda ao teu pai nesta parte.

Vai aparecer algo como:

```
A central esta a correr. Abre no telemovel: http://192.168.1.45:8080
```

Abre esse endereço no browser do telemóvel (tem de estar no mesmo Wi-Fi). Guarda-o nos favoritos ou adiciona-o ao ecrã inicial.

### 3. Não deixar a Samsung matar o servidor

A Samsung fecha apps em segundo plano para poupar bateria. Para isso não acontecer:

1. **Definições > Aplicações > Termux > Bateria**: escolhe **Sem restrições**.
2. **Definições > Assistência do dispositivo > Bateria > Limites de utilização em segundo plano**: põe o Termux em **Aplicações nunca em suspensão**.

### 4. Arrancar sozinho quando o tablet liga

Abre a app Termux:Boot uma vez (só para ela se ativar). Depois, no Termux:

```
mkdir -p ~/.termux/boot
echo '~/central/iniciar.sh' > ~/.termux/boot/central.sh
chmod +x ~/.termux/boot/central.sh
```

### 5. O endereço não mudar

O router pode dar um IP diferente ao tablet de vez em quando. Para isso não acontecer, nas definições do Wi-Fi do tablet escolhe **IP estático**, ou pede ao teu pai para reservar o IP no router.

## Estilo Jarvis e modo conversa

- Na roda dentada > Assistente, escolhe **Mordomo (estilo Jarvis)**: "Certamente, senhor.", "Lamento incomodar, senhor, mas são horas de acordar."
- **Modo conversa**: depois de ele responder, fica 8 segundos à escuta. Podes continuar a falar sem repetir o nome. Diz "esquece" para fechar.
- "Porque é que me acordaste?" explica que alarme foi e o que tens nesse dia. "Obrigado" também tem resposta.

## Ecrã Jarvis, câmara e luzes

- Quando falas com ele, abre o **ecrã Jarvis**: uma esfera animada que muda quando ouve, pensa e fala, com as horas, o tempo e a agenda. "Modo Jarvis" abre-o; "fecha-te" fecha-o; também fecha sozinho. Desliga-se em roda dentada > Dispositivos.
- **"O que é isto?"**, "em que estou a trabalhar?", "olha para isto": liga a câmara da frente, tira uma foto e o Claude diz o que vê (precisa do Claude ligado).
- **Fita LED com WLED**: escreve o IP em Dispositivos. "Luz vermelha", "põe a luz azul", "luz a 30%", "liga a luz". A fita acompanha a cor do tema da central.

## Desligar o Jarvis

- **Fechar o ecrã**: "fecha-te", "desativa o modo Jarvis", "sai do modo Iron Man", "podes ir", "modo normal" (ou tocar no ecrã)
- **Deixar de ouvir**: "Jarvis, para de ouvir" ou "modo silêncio". Para voltar a ligar, o botão do ouvido no canto de cima (vermelho = desligado).
- **Se o nome falha muitas vezes**: nas definições, em Voz, usa "Ensinar a palavra" e diz o nome 3 vezes. A central guarda as versões que a Google percebe (Jarbas, Jervis...) e passa a aceitá-las. Fala virado para o tablet e sem música alta, porque com música o reconhecimento falha muito mais.
- **Trinco "escuta"** (ligado de origem): enquanto não disseres **"escuta"**, a central ignora tudo e não mostra nada do que ouviu. Depois de "escuta" (ouves um bip) tens 15 segundos para dizer "Jarvis, ...". Também dá de seguida: "escuta, Jarvis, que horas são". Desliga-se nas definições, em Voz.
  Atenção, para não haver enganos: isto evita que a central reaja às tuas conversas, mas o reconhecimento de voz do Chrome continua a enviar o som para a Google para o transformar em texto, mesmo antes do "escuta". Se queres mesmo que nada saia do quarto, desliga a escuta (botão do ouvido) quando não precisas dela.

## Modo Iron Man

Diz **"Iron Man"** (não precisas de dizer o nome do assistente antes). Arranca o ecrã completo: sequência de arranque com som, painéis de meteorologia com a previsão por hora, sistemas (energia, servidor, rede, voz, cérebro), agenda, missões (testes, tarefas, alarme), áudio (Spotify) e um registo com tudo o que acontece. Ao centro, a esfera com radar, grelha hexagonal e anéis graduados, sempre no azul do reator. A fita LED fica azul e volta à cor do tema quando dizes "fecha-te". No telemóvel aparecem só a esfera e o topo.

## PIN da central

Liga-se no modo Iron Man > painel Sistemas > Segurança > **abrir** > PIN da central (4 a 8 números, nada de 1234 nem datas de anos). O primeiro PIN só se consegue meter no próprio tablet.

- **No tablet**: o ecrã normal (escola, estudo, horário, luzes) fica livre. O **Iron Man pede o PIN** e tranca-se quando sai do Iron Man (ou ao fim de 15 minutos sem uso). Perguntas privadas por voz ("quanto vendi hoje?") abrem o Iron Man e pedem o PIN antes de responder.
- **Noutro aparelho** (telemóvel, PC): pede o PIN para tudo. Fica lembrado 30 dias nesse aparelho.
- **Contra adivinhar**: 5 erros seguidos bloqueiam esse aparelho 5 minutos (e o dobro a cada novo erro). Mais de 20 erros numa hora bloqueiam toda a gente 15 minutos. Cada bloqueio fica nos alertas de segurança.
- **Ver quem tem acesso**: na mesma secção aparece a lista dos aparelhos com sessão aberta. "Tirar" corta o acesso. Mudar o PIN fecha todas as sessões.
- **Siri e sensores**: carrega em "Chave para Siri/sensores". A chave só aparece uma vez. No atalho da Siri, em "Obter conteúdo do URL", acrescenta o cabeçalho `X-Chave` com essa chave. Nos sensores Shelly, junta `&chave=A-CHAVE` ao fim do endereço (`.../api/sensor?nome=janela-quarto&estado=aberta&chave=...`).
- **Esqueceste o PIN?** No Termux: `rm ~/central/pin.json` e reinicia a central. Só quem tem o tablet na mão consegue fazer isto, e é essa a ideia.

Como funciona: o PIN nunca fica guardado. Fica só o hash PBKDF2-SHA256 com um sal aleatório e 200 000 iterações, em `pin.json` (fora do GitHub). Quem acerta recebe um token aleatório num cookie que o JavaScript não consegue ler (HttpOnly). Na base de dados só fica o hash desse token.

O que o PIN **não** resolve: a ligação no Wi-Fi é http, não https, por isso alguém com acesso técnico à rede de casa podia ver o PIN a passar. Em casa, com o Wi-Fi em WPA2/WPA3, o risco é baixo. E quem estiver no quarto ouve as respostas faladas.

## O que está a funcionar (Wi-Fi, internet, WhatsApp...)

"Jarvis, está tudo a funcionar?", "o WhatsApp está em baixo?", "há internet?", "o Teams não funciona". Também no Iron Man (linha Rede > estado) e no modo apagão.

A central testa a sério, a partir da tua casa: o sinal do Wi-Fi (Termux:API), o router, a internet, o DNS e se cada serviço responde (Google, WhatsApp, Instagram, TikTok, YouTube, Teams, Spotify, SNS 24, Proteção Civil, IPMA, RTP, CP, Metro de Lisboa), com o tempo que demora. Não existe nenhuma fonte pública e fiável que diga "o WhatsApp está em baixo em Portugal", por isso a central conclui só o que dá para saber: se a tua internet funciona e só um serviço falha, o problema é desse serviço; se falha tudo, é a tua internet, o router ou um apagão.

## Modo apagão

Liga-se **sozinho** quando o tablet deixa de carregar (precisa do Termux:API), ou à mão: "Jarvis, modo apagão". Para sair: o botão **"Sair do modo apagão"** no topo (ou no fundo) do ecrã, ou sozinho quando o tablet volta a carregar. A voz não funciona neste modo, porque a escuta é desligada para poupar bateria.

- **Corta o que não é importante**: fecha o Iron Man, desliga a escuta (gasta bateria e precisa de internet), pausa o Spotify, pára as atualizações do ecrã e as animações, e baixa o brilho para 25 (com Termux:API; o Android pode pedir para dares à Termux:API a autorização "Alterar definições do sistema").
- **Mostra só o essencial**: bateria e quanto tempo dura ao ritmo atual, há quanto tempo falta a luz, se há internet, rádio, notícias (as que falam de energia/apagão primeiro) e o que fazer.
- **Rádio**: Antena 1, TSF, Renascença e Antena 1 Açores/Madeira pela internet. Os endereços vêm do radio-browser.info (um diretório público que verifica as rádios todos os dias), não estão escritos à mão.
- **A verdade sobre a internet num apagão**: o router também se desliga. Só há internet se ligares o tablet ao hotspot do telemóvel, e as redes móveis também podem cair (no apagão de 28 de abril de 2025 caíram em muitos sítios). **Tem um rádio a pilhas em casa**: é a única coisa que funciona sempre, e a Proteção Civil recomenda-o no kit de emergência para 72 horas. Escreve num papel, ao lado do rádio, as frequências FM da Antena 1 e da TSF na tua zona (vêm no site de cada rádio).
- O alarme do despertador continua a funcionar (é o servidor que o toca, não o ecrã).

## Família e mapa (só no modo Iron Man)

As coisas privadas (família, mapa, loja, segurança e rede) só aparecem no modo Iron Man. O ecrã normal fica para escola, estudo e casa. Se perguntares uma coisa privada no ecrã normal ("quanto vendi hoje?"), ele abre o Iron Man e responde lá; no chat fica só "é privado", e a resposta não fica guardada no histórico.

- No painel **Família** (canto de baixo à esquerda) carrega em **+ adicionar família** e mete cada pessoa: relação (avó, tio...), nome, cidade e aniversário. Fica só no tablet, não vai para o GitHub.
- O painel mostra o tempo onde vivem, aniversários a chegar, há quantos dias não falas com eles e **⚠ alerta** se houver perigo perto da casa deles.
- **Mapa**: "Jarvis, mostra o mapa" ou o botão mapa. Casa a dourado, família a azul (vermelho se houver alerta), incêndios ativos a vermelho a piscar, sismos em círculos laranja. Por baixo diz sempre de que fonte vêm os dados, ou "sem dados" se a fonte falhou.
- **Ficha de cada pessoa**: toca no nome no painel Família (ou no ponto dela no mapa), ou diz "Jarvis, como está a avó Bia?". Mostra, cada parte com a fonte: o tempo agora e nas próximas 12 horas, de onde vem o vento, hoje e amanhã, nascer e pôr do sol (Open-Meteo); os avisos do IPMA com o texto e até que horas; incêndios a menos de 40 km (fogos.pt); sismos (USGS); e as notícias da terra dos últimos 3 dias (Google Notícias, com o nome do jornal). Também a distância de casa, o aniversário e há quanto tempo não falam.
- No mapa, os avisos de **agitação marítima** pintam só a costa; os outros (chuva, vento, neve, calor...) pintam a terra.
- Perguntas: "está tudo bem na casa dos avós?", "quando faz anos o tio?", "há quanto tempo não ligo à avó?", "liguei à avó" (fica anotado).
- Avisos sozinhos, de 15 em 15 minutos: incêndio a menos de 25 km da casa deles, aviso laranja ou vermelho do IPMA no distrito deles, sismo de magnitude 4 ou mais a menos de 150 km. No dia do aniversário, o resumo do dia lembra-te de ligar.
- Fontes: IPMA (avisos), fogos.pt com dados da Proteção Civil (incêndios), USGS (sismos), Open-Meteo (tempo e cidades). A central nunca inventa: se uma fonte não responde, diz que não sabe.
- **O mapa**: contorno real de Portugal e Espanha (Natural Earth, domínio público), com os **Açores** e a **Madeira** em caixas à esquerda, como nos mapas oficiais. As **setas do vento** (Open-Meteo, atualizado de meia em meia hora) apontam para onde o vento sopra: a cauda está do lado de onde vem o mau tempo. Seta laranja = rajadas de 50 km/h ou mais, vermelha = 70 ou mais. Os sismos pulsam com a magnitude ao lado.
- **Cores do IPMA no mapa**: os distritos com aviso ficam pintados a amarelo, laranja ou vermelho, e por baixo aparece o tipo (vento, precipitação, agitação marítima...). As fronteiras são aproximadas: cada sítio fica com a cor da zona do IPMA (distrito, ou zona das ilhas) cujo centro está mais perto. Para saber se uma vila concreta está dentro, confirma em ipma.pt.
- **Incêndios**: o fogos.pt passou a pedir uma chave pessoal. Pede-a em fogos.pt/api (com os teus pais) e guarda-a no Termux: `echo A-CHAVE > ~/central/fogos_token.txt`, depois reinicia a central. Sem chave, o mapa diz "incêndios: sem dados" e a central não te avisa de fogos. O próprio fogos.pt avisa que os dados não devem ser a única fonte em emergências: numa situação real, segue a Proteção Civil (prociv.gov.pt) e o 112.
- **Falta de luz**: no mapa, a tua casa fica a vermelho com "sem luz desde ..." quando o tablet deixa de carregar. Para a casa dos avós não há dados abertos fiáveis da E-REDES em tempo real, por isso não aparece (melhor nada do que inventar).

## A loja (Shopify)

"Como está a loja?", "quanto vendi esta semana?", "qual é o lucro do mês?", "há encomendas por enviar?", "gastei 15 euros em anúncios do TikTok". Quando entra uma encomenda nova, toca uma caixa registadora e ele diz o valor. No modo Iron Man, painel **Loja** > abrir: o resumo (hoje, ontem, semana, mês) e as despesas.

**Lucro real** = vendas - reembolsos - custo dos produtos - taxas - anúncios e outras despesas. O custo vem do campo **"Custo por artigo"** de cada produto na Shopify: preenche-o, senão o lucro aparece maior do que é.

Para ligar (com os teus pais, que supervisionam a conta). Desde 1 de janeiro de 2026 a Shopify já não deixa criar apps personalizadas no admin da loja; agora faz-se no **Dev Dashboard**:
1. Em **dev.shopify.com/dashboard**, entra com a mesma conta da loja (a app e a loja têm de ser da mesma organização) > **Create app** > nome `Central do quarto`
2. Na versão da app, em **Access scopes** (Admin API), marca só `read_orders`, `read_products` e `read_inventory`. Mais nada. Faz **Release** dessa versão.
3. **Install app** na tua loja (aceita as permissões)
4. Em **Settings** da app, copia o **Client ID** e o **Client secret**
5. Na central, modo Iron Man > painel **Loja** > ligar a loja: o domínio (`a-tua-loja.myshopify.com`), o Client ID, o Client secret e as taxas do teu método de pagamento > **Ligar a loja**

A central pede sozinha à Shopify uma chave que dura 24 horas e pede outra antes de acabar. Se já tinhas uma app antiga, de antes de 2026, com uma chave `shpat_`, essa continua a funcionar: cola-a no último campo em vez do Client ID e do secret.

O Client ID, o secret (ou a chave antiga) ficam em `loja_token.json` (fora do GitHub, só o Termux o lê) e só conseguem **ler**. A central não pede dados dos clientes.

## Notícias, avisos e segurança (só fontes reais)

Tudo vem de fontes oficiais, e ele diz sempre a fonte. Se uma fonte falhar, diz que não sabe em vez de adivinhar.

| Pergunta | Fonte |
|---|---|
| "Notícias", "notícias de cibersegurança / F1 / tecnologia / mundo" | Observador, Público, RTP, BBC, The Hacker News, BleepingComputer... (RSS). Em inglês, o Claude resume em português sem acrescentar nada |
| "Que ciberataques há esta semana?" | CISA (lista oficial de falhas exploradas em ataques reais) |
| "Há algum aviso?", "houve sismos?", "há incêndios perto?" | IPMA, USGS, fogos.pt (dados da Proteção Civil) |
| "Faltou a luz?" | O tablet: se deixa de carregar, provavelmente faltou a luz. Avisa sozinho, e quando a luz volta diz quanto tempo durou. Também avisa quando cai a internet |
| "A rede está segura?" | O próprio tablet: encriptação do Wi-Fi (WEP/WPA2/WPA3), WPS, portas perigosas do router. Só a tua rede |
| "Alguma coisa suspeita?" | A central regista os aparelhos que lhe acedem e avisa quando aparece um novo |
| "As janelas estão fechadas?" | Sensores de janela (ex.: Shelly Door/Window) a chamar `http://IP:8080/api/sensor?nome=janela-quarto&estado=aberta` e `...estado=fechada` (com PIN ligado, junta `&chave=...`) |

No modo Iron Man, no painel Sistemas > **segurança e casa**: os aparelhos (marca os teus com "É meu"), os alertas, a verificação da rede, a análise de links (phishing) e a verificação de palavras-passe roubadas. A palavra-passe nunca sai do aparelho: só vão os 5 primeiros carateres do hash SHA-1 (k-anonimato).

A **Hora de dormir** agora também avisa se ficou alguma janela aberta ou luz ligada. A rede e os apagões precisam da **Termux:API** (e de autorização de localização para ver o Wi-Fi).

## Voz neural (o Rosserini a soar a pessoa)

Por defeito o Rosserini usa as vozes do Microsoft Edge (Duarte ou Raquel, de Portugal), que soam muito mais naturais do que a voz do tablet. No Termux:

```
pip install edge-tts
```

Depois reinicia o servidor e escolhe a voz na roda dentada > Assistente. Precisa de internet. Se falhar, a central usa sozinha a voz do tablet. É um serviço gratuito e não oficial, por isso pode deixar de funcionar um dia. O texto que ele diz vai para a Microsoft para virar som.

## Spotify

"Põe música de estudo", "toca Travis Scott", "mete a playlist treino", "pausa", "próxima", "volume 30", "que música é esta?". No Início aparece um mini leitor, e nas rotinas há a ação **Música (Spotify)** (ex.: o Modo estudo põe lofi, a Hora de dormir pausa).

Precisa de **Spotify Premium** e do Spotify aberto num aparelho (o tablet ou o telemóvel). Desde fevereiro de 2026, as apps em modo de desenvolvimento só funcionam se **a conta que criou a app** tiver Premium ativo (se o Premium acabar, a app para), e cada app pode ter **no máximo 5 pessoas** autorizadas. O som sai por onde esse aparelho estiver ligado, por exemplo uma coluna Bluetooth.

Para ligar (uma vez):
1. Em **developer.spotify.com/dashboard**, entra com a conta Spotify e carrega em **Create app**
2. Nome: `Central do quarto`. Em **Redirect URIs** escreve exatamente `http://127.0.0.1:8080/api/spotify/callback` e carrega em Add. Em APIs, escolhe **Web API**. Aceita os termos e guarda.
3. Copia o **Client ID** (32 letras e números)
4. **No próprio tablet**, com a central aberta em `http://127.0.0.1:8080`: roda dentada > **Spotify** > cola o Client ID > Guardar > **Ligar ao Spotify** > entra e aceita
5. Se a conta que vai ouvir música não for a mesma que criou a app: na app, **User Management** > junta o nome e o email dessa conta.

A ligação fica em `spotify_token.json` (fora do GitHub). Não é preciso nenhum segredo: usa o método PKCE.

## Que IA em cada serviço (para gastar pouco)

| Serviço | Modelo | Como se paga |
|---|---|---|
| Voz do Jarvis, fotos pela câmara, resumos de notícias, jogo do modo amigos | Haiku 5.5 | Chave da API (cêntimos por mês) |
| **Conversa** (o chat completo, no telemóvel, no PC e no tablet) | Sonnet 5.5, e Opus 5.5 num toque para coisas difíceis ou código | Chave da API, com cache: o que já foi lido há pouco paga ~10% |
| Perguntas de revisão para os testes | Sonnet 5.5 | Chave da API |
| Rascunhos para as redes da loja | Sonnet 5.5, em lote (Batch API) | Chave da API, a **metade do preço** (prontos em até 24 h) |
| Claude Code (programar os teus projetos, no PC servidor) | o que escolheres no Claude Code | **Subscrição do Claude** (não a chave da API: programar gasta muitos tokens) |

Os modelos mudam-se nas definições do Claude, um por serviço. Tudo o que as regras da central percebem é grátis.

## A Conversa

Um chat como a app do Claude, mas que conhece a tua central (agenda, testes, tarefas, memória) e pode marcar coisas. Conversas guardadas, fotos (por exemplo de um exercício), pesquisa na web e "pensar mais". Abre-se no botão **Conversa** do assistente, no Iron Man (Sistemas), por voz ("Jarvis, vamos conversar") ou com `#conversa` no fim do endereço. No telemóvel, adiciona a central ao ecrã principal: o ícone tem um atalho para a Conversa. Pede o PIN e fecha no modo amigos.

## Relógio do Jarvis (para a placa ESP32)

`GET /api/relogio` devolve um resumo curto em JSON (hora, próximo teste, o que falta hoje, tarefas, alarme, estudo da semana, uma sugestão). Com o PIN ligado, o relógio entra com uma chave de aparelho no cabeçalho `X-Chave` (cria-a em Iron Man > Segurança). No modo amigos só devolve a hora.

## Trabalhos do Teams

A central lê as notificações do Teams no tablet e põe os trabalhos novos na lista de tarefas, com o prazo se vier no texto. Para isso: Definições do Android > Acesso a notificações > Termux:API. Só lê as notificações do Teams.

## Inteligência: o Claude

Quando o assistente não percebe uma pergunta ("porque é que o céu é azul?", "explica-me as equações", "e porquê?"), pergunta ao **Claude**. Também podes começar por "Claude, ..." para ir direto. O Claude pode usar a central (marcar, ver o dia, alarmes, mala, luz) e lembra-se da conversa dos últimos 15 minutos.

O que ele já percebia com regras continua grátis e instantâneo. Só as outras perguntas custam dinheiro.

Para ligar:
1. Um adulto cria uma conta em console.anthropic.com, mete saldo, **define um limite de gastos** e cria uma chave da API
2. No Termux: `./instalar_claude.sh` (a primeira vez pode demorar 10 a 30 minutos, porque compila partes no tablet)
3. Na roda dentada > **Inteligência**: cola a chave, escolhe o modelo e o máximo de perguntas por dia

A chave fica só no tablet, no ficheiro `chave_claude.txt` (fora do GitHub, e só o Termux o pode ler). Nunca é mostrada na página.

Nos TPC, o Claude está instruído para te ajudar a perceber em vez de te dar a resposta pronta.

## Rotinas

Uma rotina é **quando** acontece uma coisa → **(se)** uma condição → a central faz **estas ações**. Estão no assistente > **Rotinas** (ou na roda dentada). Podes ligá-las, desligá-las, experimentá-las, **editá-las** (frases, minutos, textos, ações) e **criar novas**, por exemplo "Cheguei a casa": quando dizes "cheguei" → liga a luz, diz o que tens amanhã e começa o cronómetro.

Vêm quatro feitas:
- **Bom dia**: quando paras o alarme, acende o ecrã e diz o que tens hoje e o tempo lá fora
- **Modo estudo**: quando dizes "modo estudo" (ou "vou estudar"), cronómetro de 45 min com a disciplina do próximo teste, e o Rosserini não te interrompe
- **Hora de dormir**: às 22:00 diz o que há amanhã e a que horas toca o alarme, e põe o ecrã em modo noite
- **Véspera de teste**: às 18:00, só se houver teste no dia seguinte, avisa-te

Como está feito (`rotinas.py`), em três camadas:
1. **Ações**: cada coisa que a central sabe fazer (`falar`, `cronometro`, `ecra`, `tarefa`...). O assistente usa-as, e um dia o Claude também.
2. **Rotinas**: guardadas na base de dados, com o gatilho (hora, alarme parado, frase dita) e a condição.
3. **Dispositivos**: quando houver uma tomada, luzes ou uma coluna, entram como ações novas, e todas as rotinas as podem usar.

## Dispositivos

Para já, uma tomada inteligente **Shelly** (para a fita LED, por exemplo). Na roda dentada > **Dispositivos**, escreve o IP da tomada e experimenta Ligar/Desligar. Depois:
- "Rosserini, liga a luz" / "apaga o led"
- nas rotinas, a ação **Tomada (luz)**

A central fala com a tomada diretamente no Wi-Fi de casa, sem internet. Para juntar outro aparelho: `dispositivos.py` + uma ação nova em `rotinas.py`.

## Despertador

No Início há o cartão **Despertador** com o próximo alarme. Em **Alarmes** crias:
- **alarmes que se repetem** (ex.: escola, de segunda a sexta às 07:15)
- **alarmes de um dia só** (ex.: viagem na sexta às 05:30). Nesse dia substituem os normais e depois desligam-se sozinhos.
- **"Amanhã não"** para saltar o alarme normal num dia.

Também por voz: "Rosserini, acorda-me sexta às 5 e meia que tenho viagem", "amanhã não me acordes", "a que horas é o meu alarme?".

O alarme vive no servidor, por isso **toca mesmo com o ecrã apagado**, desde que o tablet tenha a app **Termux:API**:

1. No F-Droid, instala **Termux:API** (tem de vir do mesmo sítio que o Termux)
2. No Termux: `pkg install termux-api`
3. Na central, em Alarmes, carrega em **Testar agora**. Deve tocar e, uns segundos depois, o Rosserini diz as horas e o que tens nesse dia.

Sem a Termux:API, o alarme só toca se a central estiver aberta com o ecrã ligado.

## Ecrã inteiro

No Chrome do tablet ou do telemóvel: menu ⋮ > **Adicionar ao ecrã principal** (ou "Instalar aplicação"). A central passa a abrir em ecrã inteiro, sem a barra do browser.

## Meter o horário das aulas de uma vez

No Termux, dentro da pasta `central`:

```
python importar_horario.py
```

Mete as aulas todas do 8.º ano. Se correres outra vez, não duplica nada. Para mudar uma aula, apaga-a no separador Horário e adiciona a nova com a área Escola.

## Quarto em 3D (privado)

O scan do quarto **nunca vai para o GitHub** (está no `.gitignore`), porque mostra o quarto por dentro. Para o pôr no tablet:

1. No Termux, uma vez: `termux-setup-storage` e `pkg install python-numpy python-pillow`
2. Passa o ficheiro `.fbx` da 3d Scanner App para a pasta Transferências do tablet
3. `python converter_quarto.py ~/storage/downloads/NOME_DO_FICHEIRO.fbx`

## Mudar de tablet sem perder os dados

Tudo o que escreveste está em `vida.db`. No tablet antigo: `cp ~/central/vida.db ~/storage/downloads/`. Passa o ficheiro para o novo (Quick Share) e lá: `cp ~/storage/downloads/vida.db ~/central/`.

## Atualizar

Quando houver novidades no GitHub:

```
cd ~/central
git pull
```

Depois fecha o servidor (Ctrl+C) e corre `./iniciar.sh` outra vez.

## Cópia de segurança

Tudo o que escreves está em `~/central/vida.db`. Se o tablet morrer, isto perde-se. De vez em quando copia esse ficheiro para outro sítio.

## Como funciona o assistente

Está em `assistente.py` e tem duas partes:

- `entender(texto)` descobre **o que queres** (mala, evento, nota, tarefa, o teu dia, testes) e tira os dados da frase: datas ("sexta", "dia 20", "de 20 a 23"), horas ("às 20h"), o destino e o título.
- `responder(...)` **faz a coisa** com os teus dados e responde.

Para o testares sem a central: `python -c "import assistente; print(assistente.entender('marca treino sexta às 18h'))"`

Para o melhorares mais tarde, só tens de trocar o `entender()`:
1. **Um modelo teu:** juntas umas 100 frases com a intenção certa e treinas um classificador (procura `scikit-learn`).
2. **A API do Claude:** com uma chave (de um adulto, com limite de gastos), o Claude percebe qualquer frase e chama as mesmas funções. A chave fica num ficheiro fora do GitHub.

## Desafios para ti (programação e encriptação)

Coisas que deixei por fazer de propósito, para seres tu a fazer:

1. ~~**PIN de acesso**~~: já está feito (vê "PIN da central"). Desafio novo: lê o `pin.py` todo e explica a alguém, por palavras tuas, porque é que guardar o hash com sal é melhor do que guardar o PIN, e porque é que 200 000 iterações tornam mais difícil adivinhar.
2. **Notas encriptadas**: um separador de diário onde o texto é guardado encriptado na base de dados.
3. **Backup automático**: um script que copia o `vida.db` todos os dias para uma pasta com a data no nome.
4. **Objetivos semanais**: definir quantas horas queres dar a cada área e ver se estás acima ou abaixo.

## Ficheiros

- `server.py`: o servidor (API e base de dados)
- `static/index.html`: a página que vês no telemóvel
- `iniciar.sh`: arranca tudo no Termux
