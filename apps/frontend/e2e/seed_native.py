"""Explicit local-only browser fixture; deploy real contracts and SQLModel rows.

Run from repository root with the project's venv Python. The fixture is sent to
an already running development API container, with compiled contract artifacts.
No production endpoint, real wallet key, or backend source is modified.
"""
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SOURCE = r'''
import asyncio, hashlib, json
from datetime import UTC, datetime, timedelta
from uuid import uuid4
from eth_account import Account
from web3 import Web3
from src.core.config import Config
from src.core.db import AsyncSessionFactory
from src.modules.auth.models import User
from src.modules.auth.utils import create_access_token
from src.modules.wallet.models import Wallet
from src.modules.home.models import Home
from src.modules.device.models import Device
from src.modules.community.models import EnergyCommunity, CommunityMembership, CommunityNode, MeterAuthorization, NativeDeployment
from src.iot.mqtt_handler import _insert_batch
from src.modules.energy.processor import EnergyProcessor
from src.modules.settlement.chain import NativeSettlementChain, binary
from src.modules.settlement.engine import key, hashed
from sqlmodel import select
from src.modules.settlement.models import SettlementBatch

async def run():
 w3=Web3(Web3.HTTPProvider(Config.WEB3_PROVIDER_URL))
 assert Config.ENVIRONMENT=='development' and w3.eth.chain_id in (31337,1337), 'Local test chains only'
 Config.BLOCKCHAIN_CONFIRMATION_BLOCKS=1
 governor,consumer=Account.create().address,Account.create().address
 for address in (governor,consumer):w3.provider.make_request('anvil_impersonateAccount',[address])
 oracle=Account.from_key(Config.BACKEND_PRIVATE_KEY).address
 for address in (governor,consumer,oracle):w3.provider.make_request('anvil_setBalance',[address,hex(10**22)])
 def send(fn,sender=governor):
  receipt=w3.eth.wait_for_transaction_receipt(fn.transact({'from':sender}))
  assert receipt.status==1
  return receipt
 def deploy(name,*args):
  artifact=ARTIFACTS[name]
  receipt=send(w3.eth.contract(abi=artifact['abi'],bytecode=artifact['bytecode']['object']).constructor(*args))
  return w3.eth.contract(address=receipt.contractAddress,abi=artifact['abi'])
 timelock=deploy('TimelockController',0,[governor],[governor],'0x'+'0'*40)
 registry=deploy('CommunityRegistry',timelock.address)
 sequence=0
 def govern(fn):
  nonlocal sequence
  sequence+=1;salt=Web3.keccak(text=f'frontend-{sequence}')
  send(timelock.functions.schedule(fn.address,0,fn._encode_transaction_data(),bytes(32),salt,0))
  return send(timelock.functions.execute(fn.address,0,fn._encode_transaction_data(),bytes(32),salt))
 cid=uuid4();policy=hashed('frontend explicit Anvil fixture 0.001 ETH/kWh')
 send(registry.functions.propose(key(cid),Web3.keccak(text='Cali frontend fixture'),binary(policy),900))
 for status in (2,3):govern(registry.functions.transition(key(cid),status,'0x'+'0'*40))
 govern(registry.functions.configurePrice(key(cid),10**15));activation=govern(registry.functions.transition(key(cid),4,governor))
 sun=deploy('SUNToken',timelock.address,timelock.address)
 settlement=deploy('CommunitySettlement',registry.address,sun.address,timelock.address,1,key(cid))
 vault=deploy('NativeSettlementVault',registry.address,settlement.address,sun.address)
 govern(settlement.functions.bindVault(vault.address));govern(registry.functions.bindProtocol(key(cid),settlement.address,vault.address,sun.address))
 govern(sun.functions.grantRole(sun.functions.MINTER_ROLE().call(),settlement.address))
 for role,address in ((registry.functions.ORACLE_ROLE().call(),oracle),(registry.functions.SETTLEMENT_ROLE().call(),oracle),(registry.functions.REGISTRAR_ROLE().call(),governor)):
  govern(registry.functions.grantRole(role,address))
 records=[];meters=[];nodes=[]
 async with AsyncSessionFactory() as db:
  users=[]
  for index,address in enumerate((governor,consumer)):
   suffix=uuid4().hex[:8];u=User(username=suffix,email=suffix+'@example.com',first_name='Productor' if index==0 else 'Consumidor',last_name='Solar',password_hash='fixture-no-password-login')
   db.add(u);await db.flush();users.append(u)
  db.add(EnergyCommunity(id=cid,name='Comunidad Solar Verificada',status='ACTIVE',proposer_id=users[0].uid,boundary_description='Infraestructura de prueba explícita en Cali',registry_address=registry.address,policy_hash=policy,boundary_hash=Web3.to_hex(Web3.keccak(text='Cali frontend fixture')),allow_simulated_telemetry=True,governance_transaction=Web3.to_hex(activation.transactionHash)))
  await db.flush()
  for index,(u,address) in enumerate(zip(users,(governor,consumer))):
   db.add(Wallet(user_id=u.uid,address=address,is_verified=True));db.add(CommunityMembership(community_id=cid,user_id=u.uid,status='ACTIVE',role='operator' if index==0 else 'member'))
   home=Home(owner_id=u.uid,name='Casa Solar' if index==0 else 'Casa Consumo',address='Calle 10 #20-30',city='Cali',installed_capacity_w=6000 if index==0 else 0)
   db.add(home);await db.flush();node=CommunityNode(community_id=cid,home_id=home.id,authorized=True);db.add(node);await db.flush();nodes.append(node)
   meter=Device(home_id=home.id,device_type='smart_meter',device_code='E2E-'+uuid4().hex,telemetry_source='SIMULATED',mqtt_client_id=uuid4().hex,status='ACTIVE');db.add(meter);await db.flush();meters.append(meter)
   db.add(MeterAuthorization(device_id=meter.id,node_id=node.id,credential_hash=hashlib.sha256(b'frontend-fixture-credential').hexdigest()))
   send(registry.functions.applyMembership(key(cid)),address)
   for status in (2,3):govern(registry.functions.setMembership(key(cid),address,status))
   govern(registry.functions.registerNode(key(cid),key(node.id),address));govern(registry.functions.authorizeMeter(key(cid),key(node.id),key(meter.device_id),True))
   token=create_access_token({'email':u.email,'user_uid':str(u.uid),'role':'user'})
   records.append({'address':address,'access_token':token,'home':str(home.id),'device':str(meter.id)})
  db.add(NativeDeployment(community_id=cid,chain_id=31337,sun_address=sun.address,settlement_address=settlement.address,vault_address=vault.address));await db.commit()
  end=datetime.now(UTC).replace(second=0,microsecond=0);end=end.replace(minute=end.minute//15*15)-timedelta(minutes=15);start=end-timedelta(minutes=15)
  messages=[]
  for seq,at in ((1,start),(2,end)):
   for index,meter in enumerate(meters):
    f=seq-1;messages.append({'schema_version':'2.0','message_id':str(uuid4()),'community_id':str(cid),'node_id':str(nodes[index].id),'source':'SIMULATED','simulation_mode':'REALTIME','units':{'grid_export_energy_kwh':'kWh','grid_import_energy_kwh':'kWh','consumption_energy_kwh':'kWh'},'device_id':str(meter.device_id),'home_id':str(meter.home_id),'sensor_type':'smart_meter','sequence_number':seq,'measured_at':at.isoformat(),'credential':'frontend-fixture-credential','data':{'grid_export_energy_kwh':5*f if index==0 else 0,'grid_import_energy_kwh':3*f if index==1 else 0,'consumption_energy_kwh':3*f if index==1 else 0}})
  await _insert_batch(db,messages);await db.commit();processor=EnergyProcessor();await processor.process_pending(db);await processor.finalize_closed_intervals(db)
  chain=NativeSettlementChain(w3);batch=await chain.service.calculate_interval(db,cid,start);await db.commit();batch_id=batch.id;chain_batch_id=batch.chain_batch_id
 # Seed fully confirmed funding using real calls. Browser tests then add deposits,
 # withdrawals, retirement and governance operations themselves.
 receipt=w3.eth.wait_for_transaction_receipt(vault.functions.deposit(10**15).transact({'from':consumer,'value':10**16}));assert receipt.status==1
 async def reconcile():
  async with AsyncSessionFactory() as db:
   await chain.audit_native(db,cid);await chain.index_native(db,cid);await db.commit()
 async def advance(rounds=8):
  for _ in range(rounds):
   await chain.process_native_outbox(AsyncSessionFactory,100);w3.provider.make_request('evm_mine',[]);await reconcile()
 await advance()
 govern(settlement.functions.finalize(binary(chain_batch_id)))
 await reconcile();await advance()
 send(sun.functions.approve(vault.address,5*10**18));send(vault.functions.depositSUN(5*10**18));await advance();await reconcile()
 # Worker may defer unfunded operations on exponential backoff; reset only this
 # fixture's jobs, never other communities.
 from src.modules.energy.models import OutboxEvent
 for _ in range(6):
  async with AsyncSessionFactory() as db:
   jobs=(await db.exec(select(OutboxEvent).where(OutboxEvent.payload['community_id'].astext==str(cid),OutboxEvent.event_type.like('native.%')))).all()
   for job in jobs:job.available_at=datetime.now(UTC)-timedelta(seconds=1);job.locked_at=None
   await db.commit()
  await advance(1)
 print(json.dumps({'community':str(cid),'batch':str(batch_id),'registry':registry.address,'timelock':timelock.address,'sun':sun.address,'vault':vault.address,'settlement':settlement.address,'producer':records[0],'consumer':records[1]}))
asyncio.run(run())
'''
if __name__ == '__main__':
    artifacts = {}
    for name in ['TimelockController', 'CommunityRegistry', 'SUNToken', 'CommunitySettlement', 'NativeSettlementVault']:
        artifacts[name] = json.loads((ROOT / 'contracts/out' / f'{name}.sol' / f'{name}.json').read_text())
    payload = 'ARTIFACTS=json.loads(' + repr(json.dumps(artifacts)) + ')\n' + SOURCE
    payload = 'import json\n' + payload
    command = ['docker', 'compose', '-f', 'infrastructure/docker/compose.prototype.yml', 'exec', '-T', '-e', 'NO_PROXY=localhost,127.0.0.1,anvil,timescaledb,redis,mosquitto', '-e', 'no_proxy=localhost,127.0.0.1,anvil,timescaledb,redis,mosquitto', 'api', 'python', '-']
    compose = ['docker', 'compose', '-f', 'infrastructure/docker/compose.prototype.yml']
    subprocess.run([*compose, 'stop', 'worker'], cwd=ROOT, check=True, capture_output=True)
    try:
        result = subprocess.run(command, input=payload, text=True, capture_output=True, cwd=ROOT)
    finally:
        subprocess.run(['docker', 'start', 'solar-prototype-worker-1'], cwd=ROOT, check=False, capture_output=True)
    if result.returncode:
        raise SystemExit(result.stderr[-6000:])
    data = json.loads(result.stdout.strip().splitlines()[-1])
    target = ROOT / 'apps/frontend/e2e/.native-fixture.json'
    target.write_text(json.dumps(data, indent=2))
    env_path = ROOT / 'apps/frontend/.env.local'
    updates = {'VITE_CHAIN_ID': '31337', 'VITE_REGISTRY_ADDRESS': data['registry'], 'VITE_TIMELOCK_ADDRESS': data['timelock']}
    existing = env_path.read_text().splitlines() if env_path.exists() else []
    retained = [line for line in existing if line.split('=', 1)[0] not in updates]
    env_path.write_text('\n'.join(retained + [f'{key}={value}' for key,value in updates.items()]) + '\n')
    print('Created local contract and SQLModel fixture:', target)
