# Cloud Computing Practical Assignment — Screenshot Checklist

Use this checklist to capture all **10 required screenshots** for your college practical submission. Each item explains **where to navigate**, **what must be visible**, and **how to verify** before taking the screenshot.

---

## 1. Application Running Locally
- **Where to capture:** Your Windows browser (`http://127.0.0.1:5000`) alongside or after running `python app.py` in PowerShell.
- **What must be visible:**
  - Browser address bar showing `http://127.0.0.1:5000`.
  - Top header badge showing **`Local Mode: SQLite (.data/students.db)`**.
  - At least 1–2 sample student records added locally, plus the confirmation banner (e.g., *"Student record for '...' was added successfully"*).
  - *(Optional bonus)* Keep the PowerShell window visible in the background showing `Running on http://127.0.0.1:5000`.

---

## 2. EC2 Instance in Running State
- **Where to capture:** **AWS Management Console &rarr; EC2 &rarr; Instances**.
- **What must be visible:**
  - The instance launched by your Auto Scaling Group selected in the list.
  - **Instance state:** `Running` (green check icon).
  - **Status check:** `2/2 checks passed`.
  - **Public IPv4 address** and **Instance ID** visible in the details pane below.

---

## 3. Connection / Terminal Showing Application Deployment
- **Where to capture:** **EC2 Instance Connect** browser terminal (or SSH terminal from PowerShell).
- **Commands to run before taking the screenshot:**
  ```bash
  sudo systemctl status student-app --no-pager
  sudo systemctl status nginx --no-pager
  curl -s http://127.0.0.1:8000/health && echo ""
  ```
- **What must be visible:**
  - Terminal prompt showing `ec2-user@ip-...`.
  - `student-app.service` status showing **`active (running)`**.
  - `nginx.service` status showing **`active (running)`**.
  - JSON health response: `{"service":"cloud-student-records","status":"healthy","storage_backend":"dynamodb"}`.

---

## 4. Application Opened from the EC2-Hosted Endpoint
- **Where to capture:** Your web browser opened to `http://<EC2_PUBLIC_IPV4_ADDRESS>`.
- **What must be visible:**
  - Browser address bar clearly showing the **EC2 Public IPv4 address** (`http://...`, not `127.0.0.1`).
  - Top header badge showing **`AWS Mode: Amazon DynamoDB`**.
  - At least 2 student records created through the EC2 web interface.

---

## 5. DynamoDB Table and Sample Item(s)
- **Where to capture:** **AWS Management Console &rarr; DynamoDB &rarr; Tables &rarr; `StudentRecords` &rarr; Explore table items**.
- **What must be visible:**
  - Table name: **`StudentRecords`**.
  - Partition key column: **`student_id`** (UUID strings).
  - The attributes **`name`**, **`email`**, **`course`**, and **`created_at`** matching the records you added in Screenshot #4.

---

## 6. CloudWatch Metric Graph
- **Where to capture:** **AWS Management Console &rarr; CloudWatch &rarr; Metrics &rarr; All metrics &rarr; EC2 &rarr; Per-Instance Metrics** (or **By Auto Scaling Group**) &rarr; select **`CPUUtilization`**.
- **What must be visible:**
  - Line graph plotting **`CPUUtilization`**.
  - Instance ID or Auto Scaling Group name in the legend below the graph.
  - Time range selector (e.g., `1h` or `3h`).
  - *Note:* Basic EC2 monitoring reports data points every **5 minutes**, so wait 5–10 minutes after instance launch before capturing.

---

## 7. CloudWatch Alarm Configuration / State
- **Where to capture:** **AWS Management Console &rarr; CloudWatch &rarr; Alarms &rarr; All alarms** (click the alarm created automatically by your Auto Scaling target-tracking policy, such as `TargetTracking-student-records-asg-AlarmHigh-...`).
- **What must be visible:**
  - Alarm name, state (`OK`, `In alarm`, or `Insufficient data`), and threshold condition (e.g., `CPUUtilization > 50` for scale-out alarm).
  - The threshold line on the alarm metric chart and associated Auto Scaling action.

---

## 8. EC2 Launch Template
- **Where to capture:** **AWS Management Console &rarr; EC2 &rarr; Launch Templates &rarr; `student-records-launch-template` &rarr; Details tab**.
- **What must be visible:**
  - Launch Template Name and ID.
  - Amazon Linux 2023 AMI ID, instance type (e.g., `t2.micro` or `t3.micro`), Security Group, and **IAM instance profile** (`StudentRecordsEC2Role`) under details/advanced details.

---

## 9. Auto Scaling Group Showing Minimum, Desired, and Maximum Capacity
- **Where to capture:** **AWS Management Console &rarr; EC2 &rarr; Auto Scaling Groups &rarr; `student-records-asg` &rarr; Details tab**.
- **What must be visible:**
  - Auto Scaling Group name (`student-records-asg`).
  - **Group details** section clearly showing:
    - **Desired capacity:** `1`
    - **Minimum capacity:** `1`
    - **Maximum capacity:** `2`

---

## 10. Scaling Policy and Scaling Activity / History
- **Where to capture:**
  - **Part A (Scaling Policy):** **EC2 &rarr; Auto Scaling Groups &rarr; `student-records-asg` &rarr; Automatic scaling tab** showing the Target Tracking Scaling Policy (`Average CPU utilization`, target value **`50`**%, warmup **`180`** seconds).
  - **Part B (Activity History):** **EC2 &rarr; Auto Scaling Groups &rarr; `student-records-asg` &rarr; Activity tab** under **Activity history**, showing `Successful` instance launch event (`Launching a new EC2 instance: i-...`).
  - *(Tip: You can capture both tabs or combine them into your practical report for item #10.)*
