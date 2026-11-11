export type {
  BatchView,
  AllocationView,
  ClaimView,
  FundingView,
  ParticipantStatement,
  UserMeModel,
  HomeCreateModel,
  EnergyIntervalReadModel,
  EnergyCreditReadModel,
} from "./generated";
export interface Community {
  registry_address?: string | null;
  id: string;
  name: string;
  status: string;
  proposer_id: string;
  boundary_description: string;
  topology: string;
  interval_seconds: number;
  policy_hash: string | null;
  boundary_hash: string | null;
  allow_simulated_telemetry: boolean;
  sun_per_kwh: string;
  loss_factor: string;
  temporal_policy: string;
}
export interface Home {
  id: string;
  name: string;
  address: string;
  city: string;
  country: string;
  timezone: string;
  installed_capacity_w: number;
  has_battery: boolean;
  status: string;
}
export interface Device {
  id: string;
  device_id: string;
  home_id: string;
  device_code: string;
  device_type: string;
  telemetry_source: string;
  status: string;
}
export interface Node {
  id: string;
  home_id: string;
  community_id: string;
  status: string;
  chain_node_id?: string;
  authorized?: boolean;
}
export interface NativeWallet {
  address: string;
  chain_id: number;
  block_number: number;
  wallet_wei: string;
  available_wei: string;
  reserved_wei: string;
  earnings_wei: string;
  sun_units: string;
  escrow_sun_units: string;
  reserved_sun_units: string;
  price_wei_per_kwh: string;
  asset: string;
  notice: string;
  contracts: {
    community_id: string;
    chain_id: number;
    sun_address: string;
    vault_address: string;
    settlement_address: string;
  };
}
export interface Health {
  device_id: string;
  source: string;
  device_status: string;
  online: boolean;
  last_authenticated_telemetry: string | null;
  last_quality: string | null;
  latency_seconds: string | null;
  quality_counts: Record<string, number>;
  intervals: Array<{
    id: string;
    start: string;
    end: string;
    quality: string;
    eligible_export_wh: number;
    settlement_input_ready: boolean;
  }>;
}
export interface Prepared {
  chain_id: number;
  from?: string;
  to: string;
  data: string;
  value: string;
  status: string;
  timelock?: string;
  delay_seconds?: number;
  operation_id?: string;
  schedule?: { to: string; data: string; value: string };
  execute?: { to: string; data: string; value: string };
}
export interface NativeTransaction {
  id: string;
  transaction_hash: string;
  action: string;
  status: string;
  chain_id: number;
  created_at: string;
}
export interface Operation {
  job_id: string;
  action: string;
  status: string;
  attempts: number;
  last_error: string | null;
  transaction_hash: string | null;
  chain_status: string | null;
  operation_id: string | null;
}
export interface Policy {
  id: string;
  policy_hash: string;
  price_wei_per_kwh: string;
  interval_seconds: number;
  rules: unknown;
  governance_reference: string;
}
