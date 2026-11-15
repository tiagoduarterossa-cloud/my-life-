# A minha central

Servidor pessoal que corre num Galaxy Tab S6 Lite antigo. Abre-se no telemóvel ou no PC pelo Wi-Fi de casa.

Tem seis separadores, com um visual ao estilo iOS (claro ou escuro, conforme o tema do aparelho):

- **Início**: o ecrã principal. Relógio grande, o tempo lá fora (Open-Meteo, sem conta nem chave), o que tens agora e a seguir, o próximo teste em contagem decrescente, tarefas urgentes e o tempo de hoje. Tem oito cores à escolha: roxo neon (por defeito), azul, ciano, verde, pôr do sol, vermelho, Aurora (vai mudando de cor sozinho) e Céu (muda com a hora do dia). Ao fim de uns minutos sem mexer entra em modo repouso: relógio gigante, data, temperatura, o que tens agora e o próximo teste. Na roda dentada escolhes o tema, a cidade e as horas em que o ecrã fica sempre ligado; fora dessas horas fica preto, só com o relógio.
- **Tarefas**: tudo o que tens de fazer, com área, prioridade e prazo. As atrasadas aparecem a vermelho.
- **Horário**: calendário do mês com os testes a amarelo e os 3 dias antes de cada teste marcados para estudar (verde se estudaste, vermelho se faltaste). Grelha das aulas igual à da escola, com a aula de agora destacada. E os blocos fixos da semana (aulas, treinos, almoço, estudo).
- **Estudo**: cronómetro de estudo (15, 25, 45 ou 60 min) que, ao terminar, preenche sozinho o diário com a disciplina e os minutos. Lista de testes com contagem dos dias e quanto já estudaste para cada um (conta as sessões do diário dessa disciplina). E o diário de estudo. Cada sessão guarda a disciplina, o que estudaste, como correu e as dúvidas que ficaram. O tempo entra sozinho no separador Tempo, na área Escola.
- **Tempo**: registas quanto tempo deste a cada área e vês o total dos últimos 7 dias.
- **Quarto**: o quarto em 3D, a partir de um scan LiDAR do iPhone. Roda com um dedo, aproxima com dois. Vista 3D, planta vista de cima, teto, e a luz LED na cor do tema. O visualizador é WebGL puro, sem bibliotecas, por isso funciona sem internet.
- **Roupa**: cola o link da loja e a foto aparece sozinha (se a loja deixar). Todas as peças, onde estão guardadas e se estão arrumadas, para lavar ou emprestadas. Toca na etiqueta para mudar o estado.

Só usa Python, sem bibliotecas extra. Os dados ficam no ficheiro `vida.db`, dentro do tablet. Nada vai para a internet.

## Instalar no tablet

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

## Desafios para ti (programação e encriptação)

Coisas que deixei por fazer de propósito, para seres tu a fazer:

1. **PIN de acesso**: agora qualquer pessoa no Wi-Fi de casa consegue abrir a central. Mete um PIN. Pista: guarda só o *hash* do PIN (procura `hashlib` e `pbkdf2_hmac`), nunca o PIN em texto.
2. **Notas encriptadas**: um separador de diário onde o texto é guardado encriptado na base de dados.
3. **Backup automático**: um script que copia o `vida.db` todos os dias para uma pasta com a data no nome.
4. **Objetivos semanais**: definir quantas horas queres dar a cada área e ver se estás acima ou abaixo.

## Ficheiros

- `server.py`: o servidor (API e base de dados)
- `static/index.html`: a página que vês no telemóvel
- `iniciar.sh`: arranca tudo no Termux
