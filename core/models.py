from dataclasses import dataclass


@dataclass(frozen=True)
class Wall:
    position: tuple[int, int]
    orientation: str


@dataclass
class Player:
    id: int
    name: str
    position: tuple[int, int]
    target_axis: int
    target_value: int
    remaining_walls: int
