from __future__ import annotations

from typing import Any

import Pyro5.api

from network.config import logger


class Broadcaster:
    """Gerenciador de notificações assíncronas (callbacks) do servidor para os clientes.

    Implementa o padrão Observer / Publisher-Subscriber distribuído através de chamadas
    remotas 'oneway' do Pyro5, garantindo que o servidor nunca bloqueie aguardando
    respostas dos clientes e detectando desconexões abruptas de forma resiliente.
    """

    @staticmethod
    def broadcast(
        callbacks: list[tuple[int, str]],
        action_name: str,
        *args: Any,
        timeout: float = 3.0,
        **kwargs: Any,
    ) -> list[int]:
        """Envia uma notificação assíncrona (oneway) para todos os clientes informados.

        Caso ocorra falha de comunicação com algum cliente, ele é registrado na lista
        de clientes inativos ('dead_players') para posterior purga e tratamento pelo servidor.

        Args:
            callbacks: Lista de tuplas (player_id, callback_uri) dos clientes destinatários.
            action_name: Nome do método de callback a ser invocado no cliente remoto.
            *args: Argumentos posicionais para o callback.
            timeout: Tempo limite em segundos para cada chamada remota.
            **kwargs: Argumentos nomeados para o callback.

        Returns:
            Lista de IDs dos jogadores cujos callbacks falharam (clientes mortos).
        """
        dead_players: list[int] = []

        for pid, uri in callbacks:
            try:
                with Pyro5.api.Proxy(uri) as proxy:
                    proxy._pyroTimeout = timeout
                    proxy._pyroOneway.add(action_name)
                    method = getattr(proxy, action_name, None)
                    if method is not None:
                        method(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Falha ao enviar callback '%s' para jogador %d (%s): %s",
                    action_name,
                    pid,
                    uri,
                    exc,
                )
                dead_players.append(pid)

        return dead_players

    @staticmethod
    def notify_one(
        uri: str,
        action_name: str,
        *args: Any,
        timeout: float = 2.0,
        **kwargs: Any,
    ) -> bool:
        """Envia uma notificação assíncrona direcionada a um cliente específico.

        Args:
            uri: URI Pyro5 do cliente de destino.
            action_name: Nome do método de callback a ser executado no cliente.
            *args: Argumentos posicionais.
            timeout: Tempo limite em segundos.
            **kwargs: Argumentos nomeados.

        Returns:
            True se a mensagem foi despachada com sucesso, False caso ocorra falha.
        """
        try:
            with Pyro5.api.Proxy(uri) as proxy:
                proxy._pyroTimeout = timeout
                proxy._pyroOneway.add(action_name)
                method = getattr(proxy, action_name, None)
                if method is not None:
                    method(*args, **kwargs)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Falha ao enviar notificação direta '%s' para %s: %s",
                action_name,
                uri,
                exc,
            )
            return False
