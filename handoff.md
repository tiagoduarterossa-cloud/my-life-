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
- **Modo viagem** (Iron Man, com PIN): marcar uma viagem (destino, datas, moeda, link para um guia) no botão "+ viagem" do painel Missões ou por voz ("Jarvis, nova viagem para Madrid de 3 a 7 de março"). Faz a mala com a roupa do separador Roupa conforme o clima, com caixas para marcar, as peças que estão para lavar e coisas postas à mão. Mostra o tempo (previsão do Open-Meteo só quando cobre a viagem toda; antes disso, o que fez nas mesmas datas do ano passado, dito como tal), a hora local e o câmbio do BCE (frankfurter.app). Entre a partida e a volta os alarmes de todos os dias e as rotinas com hora ficam em pausa (no dia da partida e no da volta tocam normalmente); os alarmes especiais com data tocam sempre. Voz: "modo viagem", "quantos dias faltam para a viagem?", "o que falta na mala?". Os dados da viagem ficam só no vida.db, nunca no código.
- **Modos do Jarvis** (`modos.py`, ecrã `#modo`, botões em "Modos" no ecrã inicial):
  - Estudo: a rotina "Modo estudo" (ou o botão) abre um ecrã com o cronómetro, o teste dessa disciplina, música de estudo e perguntas. Os avisos ficam guardados até saíres. No fim regista no diário; há "mais 25 min" e pausa de 5 min.
  - Revisão: "Jarvis, faz-me perguntas de Matemática". O Claude faz 6 perguntas de escolha múltipla (saída JSON estruturada) a partir do teste e do diário dos últimos 60 dias; se não houver matéria, pede-a. O ecrã avisa que as perguntas são de IA.
  - Amigos: "Jarvis, modo amigos". Esconde tarefas, testes e agenda; regras, rotinas e a ferramenta `central` do Claude não respondem a nada pessoal (`modos.PESSOAIS`) e o Claude esquece as conversas de antes. Tem relógio, música e jogo de cultura geral. Para sair, com PIN ativo, pede o PIN (`/api/modo`).
  - Treino: "Jarvis, modo treino de 10 rondas de 30 segundos com 15 de descanso". Conta em voz alta, apita nos últimos 3 s e regista em Desporto (só a partir de 1 minuto).
- **Claude com internet e custos reais**: o Claude (plano B, Haiku 5.5 por defeito) tem a pesquisa na web da Anthropic (interruptor nas definições: desligada, até 1 por pergunta por defeito, ou até 3; localizada em Portugal) e diz a fonte. A central soma o `usage` de cada resposta (todas as voltas, incluindo fotos e resumos de notícias) com os preços oficiais e guarda por mês na tabela `ia_custos`. Aparece nas definições do Claude e por voz ("quanto gastei no Claude este mês?"). Os resumos de notícias passaram a contar para o limite diário. Precisa de `anthropic>=1.1.0` (o `atualizar.sh` atualiza).
- **Cópias de segurança do vida.db**: uma por dia, verificada e comprimida, em `backups/` (14 dias e 6 meses). Com `termux-setup-storage` vai também para Armazenamento interno/Central/backups, que sobrevive a desinstalar o Termux. Aparece em "O que está a funcionar" e por voz ("Jarvis, faz uma cópia de segurança", "quando foi a última cópia de segurança?"). Restaurar: parar a central, `gunzip -c backups/vida-AAAA-MM-DD.db.gz > vida.db`, iniciar.

## Custos

Só o Claude custa dinheiro (API da Anthropic, saldo pré-pago numa conta de adulto, separada de qualquer subscrição do Claude). Tudo o resto é gratuito: Iron Man, mapa, modos, cronómetros, regras, IPMA, Open-Meteo, USGS, BCE, rádio, notícias, fogos.pt, voz. O Spotify só é controlado com conta Premium.
- Haiku 5.5: ~0,04 cêntimos por pergunta; cada pesquisa na web +1 cêntimo, mais os tokens dos resultados (é o que mais pesa). Revisão e jogo: <0,1 cêntimos por ronda no Haiku; no Opus ~2 a 3 cêntimos.
- Um mês normal (20 perguntas/dia, pesquisa até 1): de ~1,75 $ (se pesquisar em 1 de cada 4 perguntas) a ~6 $ (se pesquisar em todas). Com a pesquisa desligada: ~0,25 $.
- O limite de pesquisas vale para a pergunta inteira (todas as voltas do tool runner): gasto o orçamento, as voltas seguintes vão com `tool_choice: none`. O limite diário de perguntas fica guardado (config `ia_uso`) e não volta a zero quando a central reinicia.
- Máximo com o limite de 100/dia e uma pesquisa em cada: ~31 $/mês (com limite de 30/dia: ~10 $). O limite de gastos na consola da Anthropic continua a ser a proteção final.
- Quando as regras percebem a frase, não há custo. Paga-se só nas perguntas que as regras não percebem, nas frases começadas por "Claude, …", na revisão/jogo, nas fotos e nos resumos de notícias em inglês.
- O contador real está nas definições do Claude (tabela `ia_custos`).

Falta configurar no tablet (não é código):
- Na consola da Anthropic: pôr um limite de gastos mensal (ex.: 10 $). Nas definições do Claude: baixar o limite diário para 30.
- Ligar o Spotify (definições).
- Ligar a loja (Iron Man > Loja).
- Pedir a chave do fogos.pt e guardá-la em `fogos_token.txt`.
- Dar à Termux:API as autorizações de localização, notificações e "Alterar definições do sistema" (para o brilho).
- Correr `termux-setup-storage` uma vez, para as cópias irem também para o armazenamento do tablet.
- De vez em quando, copiar um ficheiro de Central/backups para o computador ou para a nuvem. Se o tablet morrer, as cópias morrem com ele.
- Ter um rádio a pilhas em casa, com as frequências FM escritas num papel.

## Ficheiros

- `server.py`: servidor HTTP (só biblioteca padrão), todos os endereços `/api/...`, as regras do PIN e as tarefas em segundo plano.
- `assistente.py`: percebe as frases (`entender`) e responde (`_responder`). A ordem das regras importa. `PRIVADAS` diz o que só responde com PIN.
- `ia.py`: Claude como plano B quando as regras não percebem. Usa a ferramenta `central` e esconde as conversas privadas a quem não tem PIN.
- `familia.py`: familiares, perigos perto da casa deles, mapa, ficha (`detalhe`) e a vigia de 15 em 15 minutos.
- `avisos.py`: IPMA (distritos e ilhas, terra e mar), USGS, fogos.pt (chave), vento, energia e apagões (Termux:API).
- `modos.py`: modos do Jarvis (estado do modo amigos guardado em config `modo_amigos`, o que fica escondido em `PESSOAIS`, contexto da revisão). As perguntas da revisão e do jogo são feitas em `ia.gerar_perguntas`.
- `viagem.py`: modo viagem (viagens, mala, tempo, câmbio, casa em pausa). `alarmes.py` e `rotinas.py` perguntam-lhe se estás fora.
- `backups.py`: cópias diárias do vida.db (API de backup do SQLite e integrity_check).
- `pin.py`, `radio.py`, `servicos.py`, `loja.py`, `seguranca.py`, `casa.py`, `noticias.py`, `rotinas.py`, `alarmes.py`, `voz.py`, `spotify.py`, `dispositivos.py`.
- `static/index.html`: a interface toda (HTML, CSS e JS sem bibliotecas).
- `static/mapa_pt.js`: contornos do Natural Earth (domínio público).
- `static/quarto.js`: visualizador 3D do quarto.
- `iniciar.sh`, `instalar.sh`, `atualizar.sh`: no Termux, a central está em `~/central`.
- Fora do GitHub (.gitignore): `vida.db`, `pin.json`, `chave_claude.txt`, `spotify_token.json`, `loja_token.json`, `fogos_token.txt`, `radio_cache.json`, `backups/`, `static/quarto/`.

## O que mudou

Última sessão:
- Segunda revisão a tudo o que mudou nesta sessão: "ia" (do verbo ir) já não é lido como IA ("gastei 5 euros quando ia ao cinema" regista a despesa); os dias da partida e da volta deixaram de estar em pausa; "viagem de estudo" e "mochila" já não vão para o modo viagem (nem pedem PIN); "desliga a luz e liga o modo estudo" liga o modo; os modos pedidos pela Siri vão para o tablet; "de 30 a 2 de março" dá 28 de fevereiro a 2 de março; a mudança para o Haiku só mexe em quem tinha o Opus; erros de chave no gerador de perguntas com mensagem certa; pedidos sem ligação não contam nos custos; "Outras perguntas" lembra-se da matéria.
- Revisão: o limite diário do Claude deixou de voltar a zero quando a central reinicia, e o limite de pesquisas na web passou a valer para a pergunta inteira (antes valia por cada pedido à API, e uma pergunta podia fazer várias).
- Claude: o Haiku 5.5 passou a ser o modelo padrão (os tablets que tinham outro escolhido mudam uma vez, pela chave `ia_haiku_feito`). Interruptor da pesquisa na web nas definições do Claude (`ia_pesquisa`: 0 desligada, 1 por defeito, 3); desligada, o Claude diz que não sabe coisas de hoje.
- Modos do Jarvis: estudo, revisão, amigos e treino.
- Revisão dos modos: o modo amigos fica guardado na base de dados (sobrevive a reiniciar), cala rotinas, "bom dia", vendas e detalhes dos alertas da família; "muda para o modo X" já não desliga; frases como "vou treinar sexta" ou "tenho amigos cá sábado" já não ligam modos; sair a meio do estudo pede o registo; os avisos urgentes (família) aparecem mesmo no modo estudo; quando o Claude liga um modo, o ecrã muda.
- Claude com pesquisa na web e contador de custos reais.
- Modo viagem.
- Corrigido "de 3 a 7 de março": dava 3 a 7 do mês seguinte, porque o mês só ficava no último dia.
- Cópias de segurança automáticas do vida.db (`backups.py`, `/api/backups`, voz e linha em "O que está a funcionar").

Sessão anterior (resumo dos commits):
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
- **OpenJarvis (Stanford, visto num TikTok)**: não serve para a central. Só tem instaladores para macOS, Linux, WSL e Windows, usa modelos locais pelo Ollama e instala com `curl | bash`. Ficou a ideia do resumo da manhã com Gmail e Calendar (ver "Próximo passo").
- **Não pagar o Claude com um modelo local** (Ollama no tablet ou no PC, ou o plano gratuito do Gemini): posto de lado. No tablet só cabem modelos pequenos, que erram muito e falam mal português de Portugal; o Gemini gratuito pode usar as conversas para treino. Ficou o Haiku com o interruptor da pesquisa (~1 a 2 $ por mês).
- **O ambiente de testes do Claude não tem internet aberta**: tudo foi testado com servidores falsos (IPMA, USGS, fogos, rádio, Open-Meteo, notícias, Claude, Spotify, Shopify, WLED, Shelly) e Playwright. A prova final é sempre no tablet.

## Próximo passo

1. No tablet: `cd ~/central && ./atualizar.sh` (atualiza também o SDK do Claude para >=1.1.0). Depois testar o que é novo: os 4 modos (botões "Modos" no ecrã inicial), "Jarvis, quanto gastei no Claude este mês?", uma pergunta de hoje com a pesquisa ligada, e o interruptor da pesquisa.
2. Antes de 1 de dezembro: marcar a viagem no Iron Man ("+ viagem"), com o link do guia. Se o voo for cedo, marcar um alarme especial para o dia da partida (nesse dia os alarmes normais tocam, mas à hora da escola). Encher o separador Roupa a sério, senão a mala fica genérica.
3. Daqui a duas semanas: dizer quais modos se usaram mesmo. O que não se usar, sai. Daqui a um mês: ver o contador de custos e decidir entre Haiku e Opus.
4. Se alguma parte disser "sem dados" durante mais de um dia, tirar uma foto ao ecrã e ao Termux.
5. Ideias por fazer, por ordem de utilidade: resumo da manhã com Gmail (IMAP com palavra-passe de aplicação) e Google Calendar (endereço iCal secreto), só leitura e no Iron Man (falta decidir que conta e se se quer); relatório semanal do estudo (agora há dados do modo estudo); trabalhos novos do Teams (pelas notificações do Android); Tailscale; ligação entre o quarto 3D e a roupa.
6. Pensar em tornar o repositório privado (o código não tem dados pessoais, mas mostra como a central funciona).
