# Integração dos módulos KING PLUS

## Comandos slash e componentes

1. Registre a chave do módulo em `config/systems.json` com `name`, `emoji` e `enabled`.
2. Adicione o nome exato do comando slash em `config/interaction_routes.json` > `slash_commands`. Para subcomandos, use o nome qualificado completo, como `ticket abrir`.
3. Adicione prefixos exclusivos dos botões/menus em `component_prefixes`, como `ticket:`.
4. Reinicie o bot após alterar o cadastro ou rotas (são carregados na inicialização).
5. Para comandos novos, também é possível usar `@system_enabled("tickets")` de `core.system_guard`.

## Tarefas automáticas e eventos

O bloqueio central de interações **não pausa tarefas de background, eventos on_message ou rotinas já iniciadas**. Cada módulo deve verificar o estado antes de executar ações:

```python
@commands.Cog.listener()
async def on_message(self, message):
    if not self.bot.system_manager.is_enabled("niveis"):
        return
    # processamento do módulo de níveis
```

Em tarefas demoradas, consulte novamente o estado antes de cada ação irreversível.

## Segurança

O painel público deve ser publicado em canal administrativo privado. Somente o OWNER_ID consegue usá-lo, mas a mensagem fica visível a quem tiver acesso ao canal. Nunca compartilhe o token do `.env`.

## Limites

- As rotas de `interaction_routes.json` são exemplos; adapte aos comandos e custom_ids reais.
- Componentes devem usar prefixos cadastrados; modais e outras rotas específicas exigem proteção no próprio módulo.
- A proteção automática não garante bloqueio de tarefas que não consultam o gerenciador.
- O armazenamento JSON foi pensado para **uma instância do bot** com disco persistente; não execute múltiplos processos editando os mesmos arquivos.
