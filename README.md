# KING PLUS — Unificado sem painel central

Todos os sistemas recebidos foram reunidos em um projeto Python com `main.py` (iniciação) e `bot.py` (configuração, extensões e sincronização). O painel central da Fase 8 foi **arquivado apenas como referência** em `referencias/` e **não é carregado**.

## Instalar
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python main.py
```
No Windows, ative `.venv\Scripts\activate`. Preencha `DISCORD_TOKEN`; opcionalmente `GUILD_ID`. Ative os intents privilegiados **Server Members** e **Message Content** no Developer Portal.

## Estrutura
- `main.py`: token e inicialização
- `bot.py`: configuração, carregamento de extensões e sincronização
- `modules/`: tickets, enquetes, moderação, redeem, sugestões, MU
- `systems/`: níveis, reaction roles, sorteios
- `referencias/`: controle central Fase 8 **não integrado**
- `tests/`: testes originais de níveis e reaction roles

## Observações
- O pacote MU fornecido não continha `utils/config.py`; foi criado `modules/mu/config.py` para persistência JSON.
- Os módulos foram reorganizados e imports absolutos internos ajustados para reduzir colisões.
- Não foram executados testes de integração com a API Discord nem garantida compatibilidade integral dos fluxos.
- Os comandos legados de Sugestões são ocultados e `/sugestao` abre seu painel.
- O Discord limita a 100 comandos slash globais; use painéis para evitar exceder esse limite.
- Confira permissões, comandos e persistência em um servidor de testes antes de produção.
