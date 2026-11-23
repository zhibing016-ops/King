# KING PLUS — Fase 8 (pacote cumulativo 1–8)

Controle Central de Sistemas para Python e discord.py, sem SQLite.

## Instalar

1. Requer Python 3.10+.
2. `pip install -r requirements.txt`
3. Copie `.env.example` para `.env` e configure `DISCORD_TOKEN`, `OWNER_ID` e `GUILD_ID` (ID de um servidor de testes recomendado).
4. `python check_project.py` — valida JSON e rotas, sem conectar ao Discord.
5. `python main.py`
6. Use `/canal_avisos`, `/canal_logs` e `/publicar_painel_sistemas` em canal privado. Use `/sistemas` para painel privado.

## Incluído

- Painel persistente com botões de ativar/desativar, atualização e confirmação.
- Avisos no canal configurado quando um módulo muda de estado.
- Resposta ephemeral ao usuário que tentar usar uma interação mapeada de módulo desativado.
- Logs de ações e estados salvos em JSON.
- Restauração do painel e atualização da mensagem publicada após reconexão.
- Verificador de configuração (`check_project.py`) e guia de integração (`INTEGRACAO.md`).

## Observações

- As rotas incluídas são exemplos: módulos reais devem ser conectados. O bloqueio de tarefas e eventos automáticos depende de checagens próprias em cada módulo.
- Um módulo em manutenção ainda pode executar tarefas existentes se não houver integração específica.
- Necessário disco persistente para guardar alterações em `config/systems.json` e `data/`.
- Bot precisa das permissões de ver/enviar mensagens, inserir links e ler histórico nos canais utilizados.
- O pacote é uma base funcional; a validação local não substitui testes no Discord com o token do usuário.
