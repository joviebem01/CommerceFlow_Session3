"""CMA-Flow Session 3 — data-grounded, executable inter-service console.
All historical metrics are read from the two provided archives. New metrics arise
from measured executions in this process, never from screenshot constants.
"""
from __future__ import annotations
import csv, json, queue, threading, time, traceback
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import session3_pb2
from adapter_benchmark import run_adapter_comparison
from contracts import write_contract_report
from customer_archive import DEFAULT_CUSTOMERS_PATH, load_customer_archive
from deadline_check import verify_generous_deadline
from delivery_metrics import AbandonedResponseCounter
from grpc_backend import make_grpc_service
from latency_benchmark import run_latency_benchmark
from payload_benchmark import run_payload_benchmark
from reconcile import reconcile_records
from roundtrip_benchmark import run_roundtrip_benchmark
from session3_data import summary
from services import make_service
from test_wire import verify_wire
from transport import create_transport

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data'
OUT = ROOT / 'results'
OUT.mkdir(exist_ok=True)
NAVY='#203963'; DARK='#102038'; PALE='#e1eed9'; BLUE='#eef4fc'; ORANGE='#fce7d9'; GRAY='#617997'


class GUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('CMA-Flow — Session 3 Inter-Service Communication Console')
        self.geometry('1420x880');self.minsize(1050,690)
        self.info=summary();self.server=None;self.grpc_server=None;self.grpc_port=None;self.customers=None;self.measurements={};self.events=queue.Queue()
        self.abandoned_responses=AbandonedResponseCounter()
        self.action_buttons=[];self.run_all_active=False;self.run_all_steps=[];self.run_all_current=''
        self.configure(bg='white')
        style=ttk.Style(self)
        if 'clam' in style.theme_names():style.theme_use('clam')
        style.configure('TNotebook.Tab',padding=(17,11),font=('Segoe UI',10,'bold'))
        style.configure('TNotebook',background='white')
        style.configure('Treeview.Heading',background=NAVY,foreground='white',font=('Segoe UI',10,'bold'),padding=6)
        style.configure('Treeview',font=('Segoe UI',10),rowheight=27)
        banner=tk.Frame(self,bg=NAVY,height=90);banner.pack(fill='x');banner.pack_propagate(False)
        tk.Label(banner,text='CMA-Flow — Session 3 Inter-Service Communication',font=('Georgia',22,'bold'),bg=NAVY,fg='white').pack(anchor='w',padx=25,pady=(14,0))
        tk.Label(banner,text='MIT 261 Parallel and Distributed Systems  ·  archived Session 1 + Session 2  ·  measured Session 3',font=('Segoe UI',10),bg=NAVY,fg='#bfcce1').pack(anchor='w',padx=26,pady=3)
        self.tabs=ttk.Notebook(self);self.tabs.pack(fill='both',expand=True,padx=12,pady=12)
        self.frames={}
        for label in ['Pipeline','Contract','Payload size','Latency','Round trips & streaming','Adapter swap','Reconciliation','Console']:
            frame=tk.Frame(self.tabs,bg='white');self.tabs.add(frame,text=label);self.frames[label]=frame
        self.render_pipeline();self.render_contract();self.render_payload();self.render_latency();self.render_round();self.render_adapter();self.render_reconcile();self.render_console()
        self.protocol('WM_DELETE_WINDOW',self.close)
        self.after(100,self.drain)
        self.after(500,self.refresh_abandoned_response_count)
        self.log('Loaded actual Session 1 baseline and Session 2 event-stream regional results.')
        self.log('No screenshot values are used. Benchmarks require clicking Run/Measure.')

    def header(self,frame,title,buttons=()):
        head=tk.Frame(frame,bg='white');head.pack(fill='x',padx=20,pady=(17,10))
        tk.Label(head,text=title,font=('Georgia',18,'bold'),bg='white',fg=NAVY).pack(side='left')
        for text_,func in reversed(list(buttons)):
            button=tk.Button(head,text=text_,command=func,bg=NAVY,fg='white',activebackground='#395b8a',font=('Segoe UI',10),relief='flat',padx=13,pady=8)
            button.pack(side='right',padx=4);self.action_buttons.append(button)
    def note(self,parent,text_,color=PALE):
        lbl=tk.Label(parent,text=text_,bg=color,fg=NAVY,font=('Segoe UI',10),anchor='w',wraplength=1200,justify='left',padx=15,pady=11)
        lbl.pack(fill='x',padx=20,pady=(0,12));return lbl
    def table(self,parent,columns,widths=None,height=10):
        wrapper=tk.Frame(parent,bg='white');wrapper.pack(fill='both',expand=True,padx=20,pady=8)
        tbl=ttk.Treeview(wrapper,columns=columns,show='headings',height=height)
        for i,x in enumerate(columns):tbl.heading(x,text=x);tbl.column(x,width=(widths[i] if widths else 140),anchor='w')
        sb=ttk.Scrollbar(wrapper,orient='vertical',command=tbl.yview);tbl.configure(yscrollcommand=sb.set)
        tbl.pack(side='left',fill='both',expand=True);sb.pack(side='right',fill='y');return tbl
    def fill(self,tbl,rows):
        tbl.delete(*tbl.get_children())
        for i,r in enumerate(rows):tbl.insert('','end',values=r,tags=('even' if i%2==0 else 'odd',))
        tbl.tag_configure('even',background='#e7f2df');tbl.tag_configure('odd',background='white')
    def cards(self,parent,pairs):
        row=tk.Frame(parent,bg='white');row.pack(fill='x',padx=20,pady=8)
        for big,label in pairs:
            c=tk.Frame(row,bg=BLUE,highlightbackground='#d2e1f5',highlightthickness=1);c.pack(side='left',expand=True,fill='x',padx=5,ipady=8)
            tk.Label(c,text=str(big),font=('Georgia',23,'bold'),bg=BLUE,fg=NAVY).pack()
            tk.Label(c,text=label,font=('Segoe UI',10),bg=BLUE,fg=GRAY).pack()
    def work(self,job,done):
        def target():
            try:res=job();self.events.put(('done',done,res))
            except Exception as e:self.events.put(('error',str(e),traceback.format_exc()))
        threading.Thread(target=target,daemon=True).start()
    def drain(self):
        try:
            while True:
                x=self.events.get_nowait()
                if x[0]=='done':x[1](x[2])
                elif x[0]=='error':
                    self.log(x[2])
                    if self.run_all_active:self._run_all_failed(x[2])
                    messagebox.showerror('Operation failed',x[1])
        except queue.Empty:pass
        self.after(100,self.drain)
    def log(self,msg):
        stamp=time.strftime('%H:%M:%S')
        if hasattr(self,'console'):
            self.console.insert('end',f'[{stamp}] {msg}\n');self.console.see('end')
    def ensure_server(self):
        if self.server is None:self.server=make_service(self.info['rows'],self.abandoned_responses)
        return f'http://127.0.0.1:{self.server.server_port}'
    def ensure_grpc_service(self):
        if self.grpc_server is None:
            if self.customers is None:
                self.customers=load_customer_archive(DEFAULT_CUSTOMERS_PATH)
            self.grpc_server,self.grpc_port=make_grpc_service(
                self.info['rows'],
                self.abandoned_responses,
                customer_records=self.customers,
            )
        return f'127.0.0.1:{self.grpc_port}'
    def render_pipeline(self):
        f=self.frames['Pipeline'];self.header(f,'Data-backed Session 3 pipeline',[('Run available checks',self.pipeline_checks),('Start service',self.start_service)])
        i=self.info
        self.cards(f,[(i['regions'],'states'),(f"{i['transactions']:,}",'orders in archives'),(f"{i['revenue']:,.2f}",'aggregated revenue'),('PASSED' if i['passed'] else 'FAILED','Session 1 ⇔ Session 2')])
        self.note(f,'The screenshots are design references only. Values below originate from archived results; Session 3 timings are blank until measured.')

        stage_row=tk.Frame(f,bg='white');stage_row.pack(fill='x',padx=20,pady=(0,10))
        stage_buttons=[
            ('Contract',self.run_stage_contract),('Wire format',self.run_stage_wire_format),('Serve',self.start_service),('Payload size',self.payload_bench),
            ('Unary latency',self.latency_bench),('Round trips',self.round_bench),('Streaming',self.round_bench),('Adapter swap',self.adapter_bench),
            ('Deadline',self.run_stage_deadline),('Compose',self.reconcile),('Reconcile',self.reconcile),('Run everything',self.run_all_stages)
        ]
        self.stage_buttons={}
        for idx,(label,cmd) in enumerate(stage_buttons):
            btn=tk.Button(stage_row,text=label,command=cmd,bg='white',fg=NAVY,activebackground='#dfe9f7',relief='solid',borderwidth=1,font=('Segoe UI',9),padx=10,pady=7)
            btn.grid(row=0,column=idx,sticky='ew',padx=4,pady=2)
            self.stage_buttons[label]=btn
        for col in range(len(stage_buttons)):
            stage_row.grid_columnconfigure(col,weight=1)

        self.pipeline_tbl=self.table(f,['Stage','Status','Evidence or action'],[190,160,900],13)
        self.artifacts_tbl=self.table(f,['Artifact','Written by','Status','Size'],[260,270,120,140],8)
        footer=tk.Frame(f,bg='white');footer.pack(fill='x',padx=20,pady=(10,6))
        tk.Label(footer,text='Service host: ',bg='white',fg=GRAY,font=('Segoe UI',10)).pack(side='left')
        self.host_var=tk.StringVar(value='http://127.0.0.1:0')
        tk.Label(footer,textvariable=self.host_var,bg='white',fg=NAVY,font=('Segoe UI',10,'bold')).pack(side='left',padx=(0,12))
        self.stop_host_button=tk.Button(footer,text='Stop host',command=self.stop_service,bg='#e8ecf2',fg=NAVY,relief='solid',borderwidth=1,padx=10,pady=4)
        self.stop_host_button.pack(side='right')
        self.refresh_artifacts();self.update_pipeline()
    def update_pipeline(self):
        p=self.info
        reconciliation=self.measurements.get('reconciled')
        if reconciliation:
            reconciliation_status='PASSED' if reconciliation['passed'] else 'FAILED'
            reconciliation_detail=(
                f"{reconciliation['regions']} regions; "
                f"{reconciliation['transaction_count']:,} transactions; "
                f"max revenue diff S1/S2 "
                f"{reconciliation['max_differences'][1]:.3g}/"
                f"{reconciliation['max_differences'][3]:.3g}"
            )
        else:
            reconciliation_status='NOT RUN'
            reconciliation_detail='Run service composition to compare with archived files'
        session1_parquet=next((DATA/'session1').glob('regional_revenue.parquet'),None)
        session1_source='regional_revenue.parquet loaded' if session1_parquet else 'regional_revenue.parquet NOT PRESENT; loaded baseline_result.csv'
        statuses=[('Load Session 1','VERIFIED',f"{session1_source}; {p['regions']} states; {p['transactions']:,} orders"),
                  ('Load Session 2','VERIFIED',f"{p['stream_transactions']:,} event-stream transactions"),
                  ('Reconcile S1 vs S2','PASSED' if p['passed'] else 'FAILED',f"max count diff {p['max_count_diff']}; max revenue diff {p['max_revenue_diff']:.3g}"),
                  ('Contract drift check',
                   ('PASSED' if self.measurements.get('contract_drift', {}).get('passed') else 'FAILED')
                   if 'contract_drift' in self.measurements else 'NOT RUN',
                   'CSV schemas and generated protobuf descriptors; click Run drift check'),
                  ('Wire verification',
                   ('PASSED' if self.measurements.get('wire', {}).get('passed') else 'FAILED')
                   if 'wire' in self.measurements else 'NOT RUN',
                   'Live HTTP/JSON and gRPC/protobuf parity; click Wire format'),
                  ('Partition/domain key','PARTIAL',
                   'S1 state → canonical region ← S2/S3 region; Kafka partition configuration is not present in the supplied archive'),
                  ('Abandoned responses',str(self.abandoned_responses.count),
                   'Server-confirmed client disconnects/cancellations before delivery completed; since app start'),
                  ('Generous deadline',
                   ('PASSED' if self.measurements.get('deadline', {}).get('passed') else 'FAILED')
                   if 'deadline' in self.measurements else 'NOT TESTED',
                   'Same live GetRegion call with normal and explicit 30-second deadlines'),
                  ('Local HTTP + gRPC services','RUNNING' if self.server and self.grpc_server else 'NOT STARTED',
                   f"HTTP :{self.server.server_port}, gRPC :{self.grpc_port}" if self.server and self.grpc_server else 'Click Serve'),
                  ('CustomerService',
                   'RUNNING' if self.grpc_server and self.customers is not None else 'NOT STARTED',
                   f"Read-only archive resolution; {len(self.customers):,} customer IDs from {DEFAULT_CUSTOMERS_PATH.name}"
                   if self.grpc_server and self.customers is not None else 'Start gRPC service to load the customer archive'),
                  ('Payload size',
                   'MEASURED' if 'payload' in self.measurements else 'NOT RUN',
                   f"{self.measurements['payload']['regions_measured']} regions; live JSON/protobuf request and response sizes"
                   if 'payload' in self.measurements else 'Click Measure in Payload size'),
                  ('Unary RPC latency',
                   'MEASURED' if 'latency' in self.measurements else 'NOT RUN',
                   f"Local run at {self.measurements['latency']['measured_at']}; not student hardware"
                   if 'latency' in self.measurements else 'Click Benchmark in Latency'),
                  ('N+1 vs batch',
                   'MEASURED' if 'rounds' in self.measurements else 'NOT RUN',
                   f"Local run at {self.measurements['roundtrip']['measured_at']}; not student hardware"
                   if 'roundtrip' in self.measurements else 'Click Run benchmarks in Round trips'),
                  ('Streaming',
                   'MEASURED' if 'stream' in self.measurements else 'NOT RUN',
                   f"Local run at {self.measurements['roundtrip']['measured_at']}; not student hardware"
                   if 'roundtrip' in self.measurements else 'Click Run benchmarks in Round trips'),
                  ('Adapter swap',
                   'MEASURED' if 'adapter' in self.measurements else 'NOT RUN',
                   f"Local run at {self.measurements['adapter']['measured_at']}; not student hardware"
                   if 'adapter' in self.measurements else 'Click Compare in Adapter swap'),
                  ('Session 3 ⇔ S1/S2',reconciliation_status,reconciliation_detail)]
        self.fill(self.pipeline_tbl,statuses)
        self.refresh_artifacts()

    def refresh_abandoned_response_count(self):
        if hasattr(self,'pipeline_tbl'):
            for item in self.pipeline_tbl.get_children():
                values=self.pipeline_tbl.item(item,'values')
                if values and values[0]=='Abandoned responses':
                    self.pipeline_tbl.item(
                        item,
                        values=(
                            values[0],
                            str(self.abandoned_responses.count),
                            values[2],
                        ),
                    )
                    break
        self.after(500,self.refresh_abandoned_response_count)

    def refresh_artifacts(self):
        rows=[]
        files=[
            ('contract_report.json','contracts.py','not yet','-'),
            ('wire_report.json','test_wire.py','not yet','-'),
            ('deadline_report.json','deadline_check.py','not yet','-'),
            ('payload_report.json','payload_benchmark.py','not yet','-'),
            ('payload_sizes.csv','payload_benchmark.py','not yet','-'),
            ('latency_report.json','latency_benchmark.py','not yet','-'),
            ('latency_benchmark.csv','latency_benchmark.py','not yet','-'),
            ('roundtrip_report.json','roundtrip_benchmark.py','not yet','-'),
            ('roundtrip_benchmark.csv','roundtrip_benchmark.py','not yet','-'),
            ('streaming_benchmark.csv','roundtrip_benchmark.py','not yet','-'),
            ('adapter_report.json','adapter_benchmark.py','not yet','-'),
            ('adapter_comparison.csv','adapter_benchmark.py','not yet','-'),
            ('session3_reconciliation.json','compose.py','not yet','-'),
        ]
        for name,writer,status,size in files:
            path=OUT/name
            if path.exists():
                status='ready'; size=f'{path.stat().st_size:,} bytes'
            rows.append([name,writer,status,size])
        if hasattr(self,'artifacts_tbl'):
            self.fill(self.artifacts_tbl,rows)

    def run_stage_contract(self):
        self.tabs.select(self.frames['Contract'])
        self.check_contract_drift()

    def check_contract_drift(self):
        try:
            report=write_contract_report()
        except Exception as exc:
            messagebox.showerror('Contract drift check failed',str(exc))
            self.log(f'Contract drift check failed: {exc}')
            return
        self.measurements['contract_drift']=report
        self.contract_status.config(
            text=f"{'PASSED' if report['passed'] else 'DRIFT DETECTED'} — "
                 f"{sum(check['passed'] for check in report['checks'])}/"
                 f"{len(report['checks'])} contract checks passed. "
                 "See results/contract_report.json for details.",
            bg=PALE if report['passed'] else ORANGE,
        )
        self.update_pipeline()
        self.log(
            f"Contract drift check {'passed' if report['passed'] else 'detected drift'}; "
            "wrote results/contract_report.json."
        )

    def run_stage_wire_format(self):
        self.tabs.select(self.frames['Payload size'])
        self.wire_status.config(text='Wire verification running against live loopback HTTP/JSON and gRPC/protobuf services.',bg=BLUE)
        self.log('Started live HTTP/JSON and gRPC/protobuf wire verification.')

        def done(report):
            self.measurements['wire']=report
            passed=sum(check['passed'] for check in report['checks'])
            self.wire_status.config(
                text=f"{'PASSED' if report['passed'] else 'FAILED'} — "
                     f"{passed}/{report['operations_checked']} operation checks agree "
                     "across HTTP/JSON and gRPC/protobuf. See results/wire_report.json.",
                bg=PALE if report['passed'] else ORANGE,
            )
            self.update_pipeline()
            self.log(
                f"Wire verification {'passed' if report['passed'] else 'failed'}; "
                "wrote results/wire_report.json."
            )
            self._run_all_advance()

        self.work(lambda: verify_wire(self.info['rows']),done)

    def run_stage_deadline(self):
        self.log('Running the same live GetRegion call with its normal and an explicit 30-second deadline.')

        def job():
            target=self.ensure_grpc_service()
            return verify_generous_deadline(self.info['rows'],target)

        def done(report):
            self.measurements['deadline']=report
            self.update_pipeline()
            self.log(
                f"Generous deadline check {'passed' if report['passed'] else 'failed'} "
                f"for {report['operation']}({report['region']}); wrote "
                "results/deadline_report.json."
            )
            self._run_all_advance()

        self.work(job,done)

    def run_all_stages(self):
        if self.run_all_active:
            self.log('Run everything is already in progress.')
            return
        self.run_all_active=True
        self.run_all_steps=[
            ('Contract',self.run_stage_contract,False),
            ('Wire format',self.run_stage_wire_format,True),
            ('Serve',self.start_service,False),
            ('Payload size',self.payload_bench,True),
            ('Unary latency',self.latency_bench,True),
            ('Round trips and streaming',self.round_bench,True),
            ('Adapter swap',self.adapter_bench,True),
            ('Deadline',self.run_stage_deadline,True),
            ('Compose and reconcile',self.reconcile,True),
        ]
        self._set_run_all_controls(True)
        self.log('Running all stages in sequence. Benchmarks will complete one at a time.')
        self._run_all_advance()

    def _set_run_all_controls(self,disabled):
        state=tk.DISABLED if disabled else tk.NORMAL
        for button in self.action_buttons+list(self.stage_buttons.values()):
            button.config(state=state)
        self.stop_host_button.config(state=state)
        if disabled:
            self.stage_buttons['Run everything'].config(state=tk.DISABLED)

    def _run_all_advance(self):
        if not self.run_all_active:
            return
        if not self.run_all_steps:
            self.run_all_active=False
            self.run_all_current=''
            self._set_run_all_controls(False)
            self.tabs.select(self.frames['Pipeline'])
            self.log('Run everything completed successfully. All benchmark tables and reconciliation results are updated.')
            return
        name,action,is_async=self.run_all_steps.pop(0)
        self.run_all_current=name
        self.log(f'Run everything: starting {name}.')
        try:
            action()
        except Exception:
            self._run_all_failed(traceback.format_exc())
            return
        if not is_async:
            self.after(0,self._run_all_advance)

    def _run_all_failed(self,details):
        failed_stage=self.run_all_current or 'unknown stage'
        self.run_all_active=False
        self.run_all_steps.clear()
        self.run_all_current=''
        self._set_run_all_controls(False)
        self.log(f'Run everything stopped during {failed_stage}.')
        self.log(details)

    def pipeline_checks(self):
        self.measurements['pipeline_checked']=True;self.update_pipeline();self.tabs.select(self.frames['Reconciliation']);self.log('Checked archive results; Session 3 is not marked reconciled until composition is run.')
    def start_service(self):
        try:
            self.ensure_server();self.ensure_grpc_service()
            self.host_var.set(f'HTTP :{self.server.server_port}  |  gRPC :{self.grpc_port}')
            self.update_pipeline();self.log(f'HTTP and typed gRPC services started on ports {self.server.server_port} and {self.grpc_port}.')
        except Exception as e:messagebox.showerror('Host failed',str(e))

    def stop_service(self):
        if self.server or self.grpc_server:
            if self.server:
                self.server.shutdown();self.server.server_close();self.server=None
            if self.grpc_server:
                self.grpc_server.stop(0).wait()
                self.grpc_server=None;self.grpc_port=None
            self.host_var.set('HTTP / gRPC stopped');self.update_pipeline();self.log('Stopped local HTTP and gRPC hosts.')
        else:self.log('No active local host to stop.')
    def render_contract(self):
        f=self.frames['Contract'];self.header(f,'Typed protobuf/gRPC contract and source schemas',[('Run drift check',self.run_stage_contract),('Inspect contract',self.inspect_contract)])
        self.contract_status=self.note(f,'Drift check has not run. It compares archived CSV schemas and generated protobuf descriptors against the declared contracts.',BLUE)
        self.note(f,'Domain key mapping: Session 1 state → canonical region ← Session 2 region and Session 3 RegionRequest.region / RegionResponse.region. Kafka partition configuration is not present in the supplied archive.',ORANGE)
        self.note(f,'session3.proto defines the RegionalRevenue gRPC service: GetRegion and GetSummary are unary RPCs; ListRegions is server-streaming. Typed response fields are derived from the archived regional revenue data.')
        self.contract_tbl=self.table(f,['Source file','Field name','CSV sample (first record)','Inferred description'],[280,230,290,420],14)
        self.inspect_contract()
    def inspect_contract(self):
        data=[
            ['session3.proto','RPC: GetRegion','RegionRequest -> RegionResponse','Unary typed gRPC method'],
            ['session3.proto','RPC: GetSummary','google.protobuf.Empty -> SummaryResponse','Unary typed gRPC method'],
            ['session3.proto','RPC: ListRegions','google.protobuf.Empty -> stream RegionResponse','Server-streaming typed gRPC method'],
            ['session3.proto','RegionRequest.region','','Requested state or region name (string)'],
            ['session3.proto','RegionResponse.region','','Returned state or region name (string)'],
            ['session3.proto','RegionResponse.transaction_count','','Transaction count (int64)'],
            ['session3.proto','RegionResponse.revenue_total','','Aggregated revenue (double)'],
            ['session3.proto','SummaryResponse.region_count','','Number of regions (int32)'],
            ['session3.proto','SummaryResponse.transaction_count','','Total transaction count (int64)'],
            ['session3.proto','SummaryResponse.revenue_total','','Total aggregated revenue (double)'],
        ]
        for path in sorted((DATA/'Datasets').glob('*.csv')):
            with open(path,encoding='utf-8-sig',newline='') as file:
                rd=csv.DictReader(file);sample=next(rd,{})
                for name in rd.fieldnames or []:
                    v=(sample.get(name) or '')[:75]
                    data.append([path.name,name,v,'Source dataset field; CSV values are parsed as text'])
        self.fill(self.contract_tbl,data)
    def render_payload(self):
        f=self.frames['Payload size'];self.header(f,'HTTP/JSON vs typed gRPC message sizes',[('Measure',self.payload_bench)])
        self.wire_status=self.note(f,'Wire verification has not run. Use the Pipeline Wire format action to call all operations over both live transports.',BLUE)
        self.payload_status=self.note(f,'No measurements yet. Sizes compare HTTP JSON bodies with serialized protobuf messages; gRPC HTTP/2 framing and headers are excluded.',BLUE)
        self.payload_tbl=self.table(f,['RPC response','JSON body bytes','gRPC protobuf bytes','Saved bytes','Reduction'],[300,200,230,190,200],10)
    def payload_bench(self):
        def job():
            url=self.ensure_server();target=self.ensure_grpc_service()
            return run_payload_benchmark(self.info['rows'],url,target)
        def done(report):
            measurements=report['measurements']
            rows=[
                [
                    result['region'],
                    result['json_response_bytes'],
                    result['grpc_response_bytes'],
                    result['response_bytes_saved'],
                    f"{result['response_reduction_percent']:.1f}%",
                ]
                for result in measurements
            ]
            self.measurements['payload']=report;self.fill(self.payload_tbl,rows)
            self.payload_status.config(
                text=f"{'Measured' if report['passed'] else 'Measurement failed'} "
                     f"{report['regions_measured']} live regional responses at "
                     f"{report['measured_at']}. Request and response sizes are in "
                     "payload_report.json; protobuf sizes exclude HTTP/2 framing and headers.",
                bg=PALE if report['passed'] else ORANGE,
            )
            self.update_pipeline();self.log(
                f"Payload measurement {'passed' if report['passed'] else 'failed'} for "
                f"{report['regions_measured']} regions; wrote results/payload_report.json "
                "and payload_sizes.csv."
            )
            self._run_all_advance()
        self.work(job,done)
    def render_latency(self):
        f=self.frames['Latency'];self.header(f,'Measured request-response latency',[('Benchmark 100 calls',self.latency_bench)])
        self.lat_status=self.note(f,'No new benchmark run recorded. Results will be measured on this machine and are not student-hardware results.',BLUE)
        self.lat_tbl=self.table(f,['Wire transport','Calls','Median ms','Mean ms','Requests/sec (measured wall clock)','Response bytes'],[220,100,150,150,290,180],8)
    def latency_bench(self):
        def job():
            url=self.ensure_server();target=self.ensure_grpc_service()
            return run_latency_benchmark(self.info['rows'],url,target)
        def done(report):
            rows=[
                [
                    result['transport'],
                    result['calls'],
                    f"{result['median_ms']:.4f}",
                    f"{result['mean_ms']:.4f}",
                    f"{result['requests_per_second']:.2f}",
                    result['response_bytes'],
                ]
                for result in report['measurements']
            ]
            self.measurements['latency']=report;self.fill(self.lat_tbl,rows)
            self.lat_status.config(
                text=f"{'Measured' if report['passed'] else 'Measurement failed'} "
                     f"{report['calls_per_transport']} calls per transport at "
                     f"{report['measured_at']}. {report['scope']}. Results include "
                     "environment metadata in latency_report.json.",
                bg=PALE if report['passed'] else ORANGE,
            )
            self.update_pipeline();self.log(
                f"Latency benchmark {'passed' if report['passed'] else 'failed'} "
                f"({report['scope']}); wrote latency_report.json and "
                "latency_benchmark.csv."
            )
            self._run_all_advance()
        self.work(job,done)
    def render_round(self):
        f=self.frames['Round trips & streaming'];self.header(f,'N+1 requests vs batching and streaming',[('Run benchmarks',self.round_bench)])
        self.round_status=self.note(f,'No new benchmark run recorded. Measurements will use this machine and are not student-hardware results.',BLUE)
        self.round_tbl=self.table(f,['Test','Requests','Elapsed ms','Time to first row ms','Rows returned','Notes'],[230,100,140,200,150,400],8)
    def round_bench(self):
        def job():
            url=self.ensure_server();target=self.ensure_grpc_service()
            return run_roundtrip_benchmark(self.info['rows'],url,target)
        def done(report):
            rows=[
                [
                    measurement['test'],
                    measurement['requests'],
                    f"{measurement['elapsed_ms']:.3f}",
                    f"{measurement['time_to_first_row_ms']:.3f}"
                    if measurement['time_to_first_row_ms'] is not None else '—',
                    measurement['rows_returned'],
                    measurement['notes'],
                ]
                for measurement in report['measurements']
            ]
            self.measurements['roundtrip']=report
            self.measurements['rounds']=report['measurements'][:2]
            self.measurements['stream']=report['measurements'][2:]
            self.fill(self.round_tbl,rows)
            self.round_status.config(
                text=f"{'Measured' if report['passed'] else 'Measurement failed'} "
                     f"batch, N+1, HTTP streaming, and gRPC streaming at "
                     f"{report['measured_at']}; {report['scope']}. "
                     "Full environment and results are saved in roundtrip_report.json.",
                bg=PALE if report['passed'] else ORANGE,
            )
            self.update_pipeline();self.log(
                f"Round-trip benchmark {'passed' if report['passed'] else 'failed'} "
                f"for {report['regions_expected']} regions; wrote roundtrip_report.json, "
                "roundtrip_benchmark.csv, and streaming_benchmark.csv."
            )
            self._run_all_advance()
        self.work(job,done)
    def render_adapter(self):
        f=self.frames['Adapter swap'];self.header(f,'Same service interface, alternate encoding',[('Compare adapters',self.adapter_bench)])
        self.adapter_status=self.note(f,'No new adapter comparison recorded. HTTP/JSON and gRPC/protobuf are live transport adapters; payment adapter remains an interface seam only.',BLUE)
        self.adapter_tbl=self.table(f,['Adapter','Calls','Mean ms / call','Sent bytes','Received bytes','Identical responses'],[270,120,200,190,210,210],10)
    def adapter_bench(self):
        def job():
            url=self.ensure_server();target=self.ensure_grpc_service()
            return run_adapter_comparison(self.info['rows'],url,target)
        def done(report):
            rows=[
                [
                    result['transport'],
                    result['calls'],
                    f"{result['mean_ms_per_call']:.4f}",
                    result['sent_bytes'],
                    result['received_bytes'],
                    'YES' if report['identical_responses'] else 'NO',
                ]
                for result in report['transports']
            ]
            self.measurements['adapter']=report;self.fill(self.adapter_tbl,rows)
            self.adapter_status.config(
                text=f"{'Compared' if report['passed'] else 'Comparison failed'} "
                     f"both live transport adapters for {report['regions_compared']} "
                     f"regions at {report['measured_at']}. {report['scope']}. "
                     "The payment adapter remains interface-only.",
                bg=PALE if report['passed'] else ORANGE,
            )
            self.update_pipeline();self.log(
                f"Adapter comparison {'passed' if report['passed'] else 'failed'} "
                f"for {report['regions_compared']} regions; wrote "
                "adapter_report.json and adapter_comparison.csv."
            )
            self._run_all_advance()
        self.work(job,done)
    def render_reconcile(self):
        f=self.frames['Reconciliation'];self.header(f,'Three execution views, one audit trail',[('Compose & reconcile live',self.reconcile)])
        i=self.info
        self.recon_status=self.note(f,f"ARCHIVED S1 vs S2: {'PASSED' if i['passed'] else 'FAILED'} — {i['regions']} states, {i['transactions']:,} orders, revenue {i['revenue']:,.2f}; max state revenue difference {i['max_revenue_diff']:.9g}. Session 3 has not been checked yet.")
        self.recon_tbl=self.table(f,['State','S1 count','S2 count','Session 3 count','S1 revenue','S2 revenue','Session 3 revenue'],[180,100,100,160,200,200,200],15)
        self.fill(self.recon_tbl,[[r[0],r[1],r[3],'NOT RUN',f'{r[2]:,.2f}',f'{r[4]:,.2f}' if r[4] is not None else 'N/A','NOT RUN'] for r in i['rows']])
    def reconcile(self):
        def job():
            target=self.ensure_grpc_service();answer=create_transport('grpc',target).call('ListRegions')[0]['regions']
            return reconcile_records(self.info['rows'],answer,OUT)
        def done(res):
            rows,report=res;self.fill(self.recon_tbl,rows)
            self.recon_status.config(text=f"{'PASSED' if report['passed'] else 'FAILED'} — live service composition versus both archives; {report['regions']} states, {report['transaction_count']:,} orders; max count differences S1/S2 = {report['max_differences'][0]}/{report['max_differences'][2]}, max revenue differences = {report['max_differences'][1]:.3g}/{report['max_differences'][3]:.3g}.")
            self.measurements['reconciled']=report;self.update_pipeline();self.log('Wrote results/session3_reconciliation.json and session3_regional_revenue.csv')
            self._run_all_advance()
        self.work(job,done)
    def render_console(self):
        f=self.frames['Console'];self.header(f,'Verbatim actions, measurements and errors',[('Save transcript',self.save_log),('Clear',self.clear_log)])
        self.console=tk.Text(f,font=('Consolas',11),bg=DARK,fg='#e4edfc',insertbackground='white',wrap='word')
        self.console.pack(fill='both',expand=True,padx=20,pady=(0,20))
    def save_log(self):
        filename=filedialog.asksaveasfilename(defaultextension='.txt',filetypes=[('Text file','*.txt')])
        if filename:Path(filename).write_text(self.console.get('1.0','end-1c'),encoding='utf-8')
    def clear_log(self):self.console.delete('1.0','end')
    def close(self):
        if self.server:self.server.shutdown();self.server.server_close()
        if self.grpc_server:self.grpc_server.stop(0).wait()
        self.destroy()

if __name__=='__main__':
    GUI().mainloop()
