from pydantic import BaseModel


class NetworkStats(BaseModel):
    nodes: int
    edges: int
    oneway_edges: int
    bidirectional_edges: int
    length_km: float
    avg_speed_kph: float
    weak_components: int
    strong_components: int
    largest_component_nodes: int
    largest_component_ratio: float
    isolated_nodes: int
    degree_one_nodes: int
    highway_counts: dict[str, int]
    speed_source_counts: dict[str, int]
