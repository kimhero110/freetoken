# -*- coding: utf-8 -*-
"""
WitKit Sentinel: Probing Engine & Anti-Flapping State Manager (Safe Print)
------------------------------------------------------------------------
- Dynamically discovers Tailscale nodes across Windows and Linux
- Executes zero-overhead network layer & application layer probes
- State tracking with hysteresis/anti-flapping before dispatching Feishu cards
"""

import os
import sys
import time
import json
import socket
import fnmatch
import urllib.request
import urllib.error
import subprocess
from pathlib import Path
import yaml

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from feishu_ops import send_ops_alert, send_ops_recovery, send_ops_summary


class SentinelEngine:
    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = str(Path(__file__).resolve().parent / "config.yaml")
        self.config_path = Path(config_path)
        self.config = self.load_config()
        self.state_file = self.config_path.parent / ".sentinel_state.json"
        self.state = self.load_state()

    def load_config(self) -> dict:
        if self.config_path.exists():
            with open(self.config_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        return {}

    def load_state(self) -> dict:
        if self.state_file.exists():
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def save_state(self):
        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(self.state, f, indent=2)
        except Exception as e:
            print(f"[WARN] Failed to save state: {e}")

    def discover_tailscale_nodes(self) -> list:
        """Dynamically fetch all active Tailscale peers from local daemon."""
        ignore_os = self.config.get("tailscale", {}).get("ignore_os", ["android", "ios"])
        ignore_os = [x.lower() for x in ignore_os]
        ignore_patterns = self.config.get("tailscale", {}).get("ignore_name_patterns", [])

        try:
            output = subprocess.check_output(["tailscale", "status", "--json"], timeout=5)
            data = json.loads(output)
        except Exception as e:
            print(f"[WARN] Unable to execute `tailscale status --json`: {e}")
            return []

        nodes = []
        user_map = {str(k): v.get("DisplayName", "") for k, v in data.get("User", {}).items()}

        # 1. Self node
        self_node = data.get("Self", {})
        if self_node:
            os_name = (self_node.get("OS") or "").lower()
            hname = self_node.get("HostName", "")
            if os_name not in ignore_os and not any(fnmatch.fnmatch(hname.lower(), p.lower()) for p in ignore_patterns):
                ips = self_node.get("TailscaleIPs", [])
                nodes.append({
                    "id": f"self_{hname}",
                    "name": f"{hname} (本探测机)",
                    "os": os_name,
                    "ip": ips[0] if ips else "127.0.0.1",
                    "online": True,
                    "is_self": True,
                    "user": "local"
                })

        # 2. Peers
        peers = data.get("Peer", {})
        for _, p in peers.items():
            os_name = (p.get("OS") or "").lower()
            if os_name in ignore_os:
                continue

            name = p.get("HostName", "unknown")
            if any(fnmatch.fnmatch(name.lower(), p.lower()) for p in ignore_patterns):
                continue

            ips = p.get("TailscaleIPs", [])
            ip = ips[0] if ips else ""
            online = bool(p.get("Online", False))
            user_id = str(p.get("UserID", ""))
            user_name = user_map.get(user_id, "")

            nodes.append({
                "id": f"peer_{name}_{ip}",
                "name": name,
                "os": os_name,
                "ip": ip,
                "online": online,
                "is_self": False,
                "user": user_name
            })

        return nodes

    @staticmethod
    def probe_tcp_port(ip: str, port: int, timeout: int = 3) -> tuple[bool, str]:
        """Test TCP socket connection."""
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        start_time = time.time()
        try:
            s.connect((ip, int(port)))
            s.close()
            latency = int((time.time() - start_time) * 1000)
            return True, f"TCP {port} 畅通 ({latency}ms)"
        except Exception as e:
            return False, f"TCP {port} 连接失败: {e}"

    @staticmethod
    def probe_http_service(url: str, expected_status: int = 200, timeout: int = 5) -> tuple[bool, str]:
        """Test HTTP/HTTPS endpoint."""
        start_time = time.time()
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "WitKit-Sentinel/1.0 (HealthCheck)"}
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                status = resp.status
                latency = int((time.time() - start_time) * 1000)
                if status == expected_status or (expected_status == 200 and 200 <= status < 400):
                    return True, f"HTTP {status} 正常 ({latency}ms)"
                else:
                    return False, f"HTTP 状态码不符: 期望 {expected_status}, 实际返回 {status}"
        except urllib.error.HTTPError as he:
            return False, f"HTTP 错误代码 {he.code}: {he.reason}"
        except Exception as e:
            return False, f"连接异常: {e}"

    def evaluate_target(self, key: str, target_name: str, target_type: str, ip: str, is_healthy: bool, detail_msg: str, os_type: str = None):
        """State machine anti-flapping evaluation."""
        threshold = self.config.get("sentinel", {}).get("consecutive_failures_to_alert", 2)
        feishu_cfg = self.config.get("feishu", {})
        webhook = feishu_cfg.get("webhook_url")
        secret = feishu_cfg.get("secret")

        target_state = self.state.setdefault(key, {
            "fail_count": 0,
            "is_alerted": False,
            "last_healthy": True,
            "first_failed_time": None
        })

        if not is_healthy:
            target_state["fail_count"] += 1
            if target_state["first_failed_time"] is None:
                target_state["first_failed_time"] = time.time()

            print(f"  [X] [{target_name}] 探测异常 (连续第 {target_state['fail_count']}/{threshold} 次): {detail_msg}")

            if target_state["fail_count"] >= threshold and not target_state["is_alerted"]:
                print(f"  [ALERT] [{target_name}] 达到报警阈值，向飞书发送红色故障告警！")
                send_ops_alert(
                    webhook_url=webhook,
                    secret=secret,
                    target_name=target_name,
                    target_type=target_type,
                    ip=ip,
                    error_msg=detail_msg,
                    os_type=os_type
                )
                target_state["is_alerted"] = True
            target_state["last_healthy"] = False
        else:
            # Healthy
            if target_state.get("is_alerted"):
                print(f"  [RECOVERY] [{target_name}] 故障自愈，向飞书发送绿色恢复通知！")
                send_ops_recovery(
                    webhook_url=webhook,
                    secret=secret,
                    target_name=target_name,
                    target_type=target_type,
                    ip=ip,
                    recovery_msg=detail_msg,
                    os_type=os_type
                )
                target_state["is_alerted"] = False

            target_state["fail_count"] = 0
            target_state["first_failed_time"] = None
            target_state["last_healthy"] = True
            print(f"  [OK] [{target_name}] 探测正常: {detail_msg}")

    def run_sweep(self, send_summary: bool = False):
        """Execute a full monitoring sweep across all dynamic nodes and services."""
        print("\n" + "=" * 65)
        print(f"[WITKIT SENTINEL] 启动全栈巡检 - {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 65)

        # 1. Tailscale Dynamic Nodes
        nodes = self.discover_tailscale_nodes()
        print(f"[TAILSCALE] 动态发现主机节点池: 共 {len(nodes)} 台纳入监视的主机")

        node_report = []
        for n in nodes:
            name = n["name"]
            os_name = n["os"]
            ip = n["ip"]
            online = n["online"]

            # 1.1 Tailscale Heartbeat check
            if not online:
                self.evaluate_target(
                    key=f"node_{n['id']}",
                    target_name=name,
                    target_type="Tailscale 宿主机",
                    ip=ip,
                    is_healthy=False,
                    detail_msg="Tailscale 节点离线（宿主机可能断网、关机或死机）",
                    os_type=os_name
                )
                node_report.append({"name": name, "ip": ip, "os": os_name, "online": False, "status": "离线"})
                continue

            # 1.2 OS-specific port check (only if online)
            default_ports = self.config.get("tailscale", {}).get("default_ports", {})
            ports = default_ports.get(os_name, [])
            all_ports_ok = True
            port_msg = "在线活跃"

            for p in ports:
                ok, msg = self.probe_tcp_port(ip, p, timeout=2)
                if not ok:
                    all_ports_ok = False
                    port_msg = msg
                    break

            self.evaluate_target(
                key=f"node_{n['id']}",
                target_name=name,
                target_type="Tailscale 宿主机",
                ip=ip,
                is_healthy=all_ports_ok,
                detail_msg=port_msg,
                os_type=os_name
            )
            node_report.append({"name": name, "ip": ip, "os": os_name, "online": all_ports_ok, "status": port_msg})

        # 2. Service Endpoints
        services = self.config.get("services", [])
        print(f"\n[SERVICES] 巡检关键生产端点: 共 {len(services)} 项服务")
        service_report = []

        for svc in services:
            s_name = svc.get("name")
            s_type = svc.get("type", "http")
            key = f"svc_{s_name}"

            if s_type == "http":
                url = svc.get("url")
                expected = svc.get("expected_status", 200)
                timeout = svc.get("timeout_seconds", 5)
                ok, msg = self.probe_http_service(url, expected, timeout)
                self.evaluate_target(key, s_name, "HTTP 业务服务", url, ok, msg)
                service_report.append({"name": s_name, "healthy": ok, "detail": msg})

            elif s_type == "tcp":
                target = svc.get("target")
                port = svc.get("port")
                timeout = svc.get("timeout_seconds", 3)
                ok, msg = self.probe_tcp_port(target, port, timeout)
                self.evaluate_target(key, s_name, "TCP 内部端口", f"{target}:{port}", ok, msg)
                service_report.append({"name": s_name, "healthy": ok, "detail": msg})

        self.save_state()

        # 3. Optional Summary Card
        if send_summary:
            print("\n[FEISHU] 发送资源池巡检汇总大盘卡片...")
            feishu_cfg = self.config.get("feishu", {})
            online_count = sum(1 for n in node_report if n["online"])
            send_ops_summary(
                webhook_url=feishu_cfg.get("webhook_url"),
                secret=feishu_cfg.get("secret"),
                total_nodes=len(node_report),
                online_nodes=online_count,
                node_list=node_report,
                service_list=service_report
            )

        print("\n" + "=" * 65)
        print("[OK] 巡检轮次完成，状态数据已持久化。")
        print("=" * 65 + "\n")
