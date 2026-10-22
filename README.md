# Student Record Management System on AWS

**Cloud Computing Practical Assignment — Amazon EC2, DynamoDB, CloudWatch, Launch Template & Auto Scaling**

---

## 1. Project Introduction

The **Student Record Management System** is a production-structured Python Flask web application built for a college cloud computing practical assignment. It demonstrates how to build a clean CRUD web application locally on **Windows (using SQLite)** and deploy it to **Amazon EC2 (using Amazon DynamoDB)** behind **Nginx** and **Gunicorn**, managed by an **EC2 Launch Template**, **EC2 Auto Scaling Group**, and **Amazon CloudWatch**.

Key design principles:
- **Explicit Dual Storage Modes:** Runs locally with zero AWS credentials (`STORAGE_BACKEND=sqlite`) and in AWS with Amazon DynamoDB (`STORAGE_BACKEND=dynamodb`).
- **No Silent Fallback:** If DynamoDB is selected and an AWS configuration or permission error occurs, the app logs detailed diagnostics on the server and displays a safe error message—it **never** silently writes to local SQLite.
- **Zero Hardcoded Secrets:** Uses an **EC2 IAM Role (Instance Profile)** so temporary credentials are provided automatically by the EC2 instance metadata service.

---

## 2. Features

1. **Add Student Record:** Server-side validated form for Student Name, Email Address, and Course/Program.
2. **Display All Student Records:** Clean directory table showing UUID `student_id`, `name`, `email`, `course`, and `created_at` (UTC).
3. **Edit Existing Student Record:** Update a student's name, email, or course while preserving their original UUID and creation timestamp.
4. **Delete Student Record:** Remove a student record with confirmation and status feedback.
5. **Flash Notifications:** Helpful confirmation and validation banners on add, update, and delete actions.
6. **Friendly Empty State:** Clear empty-state illustration and call-to-action when no records exist.
7. **Responsive UI:** Works cleanly across desktop and mobile viewports with an active storage-mode indicator badge.
8. **Health Check Endpoint (`/health`):** Returns `HTTP 200` with JSON status (`{"status": "healthy", ...}`) for readiness verification.
9. **Safe Error Handling:** Server-side validation and error handlers that never leak stack traces or AWS credentials to visitors.

---

## 3. Architecture

### Local Development Mode (`STORAGE_BACKEND=sqlite`)
```text
[ Windows Browser (http://127.0.0.1:5000) ]
               │
               ▼
     [ Flask App (app.py) ]
               │
               ▼
[ Local SQLite DB (.data/students.db) ]
```

### AWS Cloud Deployment Mode (`STORAGE_BACKEND=dynamodb`)
```text
[ Internet User Browser (http://<EC2-Public-IPv4>:80) ]
               │
               ▼  (TCP Port 80 allowed by Security Group)
┌──────────────────────────────────────────────────────────────┐
│ Amazon EC2 Instance (Amazon Linux 2023 in Public Subnet)     │
│  Managed by EC2 Auto Scaling Group (Min: 1, Desired: 1, Max:2)│
│  Provisioned via EC2 Launch Template + User Data Script      │
│  Attached IAM Role: StudentRecordsEC2Role                    │
│                                                              │
│  [ Nginx Reverse Proxy (:80) ]                               │
│               │                                              │
│               ▼ (127.0.0.1:8000 - internal loopback only)    │
│  [ Gunicorn WSGI Server + Flask App (systemd: student-app) ] │
└──────────────┬───────────────────────────────────────────────┘
               │
               ├──► [ Amazon DynamoDB Table: StudentRecords (PK: student_id) ]
               │      (Authenticated via EC2 IAM Role temporary credentials)
               │
               └──► [ Amazon CloudWatch ]
                      (EC2 CPUUtilization metrics + Target-Tracking Alarms @ 50% CPU)
```

---

## 4. File Structure

```text
cloud-student-records/
├── app.py                        # Flask application factory, routes, validation, error handlers
├── storage.py                    # Explicit SQLite and DynamoDB storage implementations
├── requirements.txt              # Python package dependencies
├── .env.example                  # Example environment variables (no secrets)
├── .gitignore                    # Excludes .venv, .env, .data/, and caches from Git
├── .gitattributes                # Enforces LF line endings on .sh scripts for Linux EC2
├── README.md                     # Complete local + AWS Console deployment documentation
├── templates/
│   └── index.html                # Jinja2 responsive dashboard template (Add, Edit, List)
├── static/
│   └── style.css                 # Responsive stylesheet
├── deploy/
│   ├── user_data.sh              # Amazon Linux 2023 EC2 Launch Template bootstrap script
│   └── iam_policy.json           # Least-privilege IAM policy JSON for StudentRecords table
├── tests/
│   └── test_app.py               # Automated pytest suite (CRUD, validation, health, DynamoDB errors)
└── docs/
    └── SCREENSHOT_CHECKLIST.md   # Guide for capturing all 10 required assignment screenshots
```

**Why extra helper files exist:**
- `.gitattributes`: Ensures `deploy/user_data.sh` keeps Unix `LF` line endings even when edited or committed on Windows, preventing `/bin/bash^M` errors on Amazon Linux 2023.
- `deploy/iam_policy.json`: Provides a ready-to-copy least-privilege IAM policy document scoped to the `StudentRecords` DynamoDB table.

---

## 5. Prerequisites

- **Local Machine:** Windows 10/11 with **Python 3.9+** and **Git** installed.
- **GitHub Account:** To host a **public** repository (`cloud-student-records`) so EC2 User Data can clone it without SSH keys or tokens.
- **AWS Account:** Access to the AWS Management Console (EC2, DynamoDB, IAM, CloudWatch).

---

## 6. Windows Setup and Local Run Commands

Open **Windows PowerShell**, navigate into the `cloud-student-records` directory, and run the following commands:

```powershell
cd cloud-student-records
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
```

Open your browser to:
**http://127.0.0.1:5000**

### What if PowerShell blocks `Activate.ps1`?
If Windows PowerShell displays an error saying *"running scripts is disabled on this system (ExecutionPolicy)"*, choose **either** of these safe options:

- **Option A (Allow scripts for the current PowerShell window only):**
  ```powershell
  Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
  .\.venv\Scripts\Activate.ps1
  ```
- **Option B (Run directly using the virtual environment's Python executable without activating):**
  ```powershell
  .\.venv\Scripts\python.exe -m pip install -r requirements.txt
  .\.venv\Scripts\python.exe app.py
  ```

---

## 7. Local Testing Steps

### A. Run the Automated Unit Test Suite
With your virtual environment active in `cloud-student-records`:

```powershell
python -m pytest -v
```
*(Or without activating: `.\.venv\Scripts\python.exe -m pytest -v`)*

The test suite creates an isolated temporary SQLite database and verifies:
- `GET /health` returns HTTP 200 and JSON status.
- Empty state rendering when no records exist.
- Creating, listing, editing, and deleting student records.
- Server-side rejection of invalid form inputs (HTTP 400).
- DynamoDB error handling without silent SQLite fallback.

### B. Manual Local Verification
1. Start the app (`python app.py`) and visit `http://127.0.0.1:5000`.
2. Verify the top badge says **`Local Mode: SQLite (.data/students.db)`**.
3. Add 2 student records and verify the green confirmation banner appears.
4. Click **Edit** on a record, modify the course name, and click **Save Changes**.
5. Click **Delete** on a record and confirm removal.
6. Visit `http://127.0.0.1:5000/health` and verify it returns:
   ```json
   {"service":"cloud-student-records","status":"healthy","storage_backend":"sqlite"}
   ```
7. Capture **Screenshot #1 (Application running locally)**.

---

## 8. GitHub Repository Setup and Push Commands

Your EC2 instance will clone your code from GitHub during boot using `deploy/user_data.sh`.

1. Sign in to [GitHub](https://github.com/) and click **New repository**.
2. Set **Repository name** to: `cloud-student-records`
3. Set visibility to **Public** (required so EC2 can `git clone` without credentials).
4. Do **not** initialize with a README or `.gitignore` (this project already has them).
5. Click **Create repository**.
6. In **PowerShell** inside the `cloud-student-records` folder, run:

```powershell
git init
git branch -M main
git status
git add .
git commit -m "Initial commit: Student Record Management System for AWS practical"
git remote add origin https://github.com/YOUR_USERNAME/cloud-student-records.git
git push -u origin main
```
*(Replace `YOUR_USERNAME` with your actual GitHub username.)*

> **Security Check:** Before pushing, verify that `.data/` and `.env` do **not** appear in `git status`. They are excluded by `.gitignore`.

---

## 9. AWS Region Selection

1. Sign in to the **AWS Management Console**.
2. In the top-right navigation bar, select your AWS Region—for example, **Asia Pacific (Mumbai) `ap-south-1`** (or your preferred region such as `us-east-1`).
3. **Important:** Keep the **exact same region** selected while creating your **DynamoDB Table**, **Security Group**, **Launch Template**, **Auto Scaling Group**, and **CloudWatch** views.

---

## 10. DynamoDB Table Creation

1. Open the **Amazon DynamoDB** console (**Services &rarr; Database &rarr; DynamoDB**).
2. Click **Create table**.
3. Enter the exact settings below:
   - **Table name:** `StudentRecords` *(case-sensitive)*
   - **Partition key:** `student_id`
   - **Partition key type:** `String`
   - **Sort key:** Leave blank (none)
4. Under **Table settings**, select **Customize settings**:
   - **Table class:** DynamoDB Standard
   - **Capacity mode:** Choose **On-demand** (pay-per-request, no idle capacity charges for small practical workloads) or **Provisioned** (`1 RCU / 1 WCU` within AWS Free Tier).
5. Leave encryption and other settings at default and click **Create table**.
6. Wait until the table status changes to **`Active`**.
7. Click the **`StudentRecords`** table name and copy its **Amazon Resource Name (ARN)** from the **General information** section (looks like `arn:aws:dynamodb:ap-south-1:123456789012:table/StudentRecords`).

---

## 11. IAM Policy and EC2 Role Creation

Instead of putting AWS access keys in code, attach an IAM Role to EC2.

### Step 11.1 — Create the Custom Least-Privilege IAM Policy
1. Open the **IAM** console (**Services &rarr; Security, Identity, & Compliance &rarr; IAM**).
2. In the left menu, click **Policies** &rarr; **Create policy**.
3. Switch the policy editor tab to **JSON**.
4. Paste the following policy (also available in `deploy/iam_policy.json`) and replace the `Resource` ARN with your `StudentRecords` table ARN (or replace `AWS_REGION_PLACEHOLDER` and `AWS_ACCOUNT_ID_PLACEHOLDER`):

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "StudentRecordsTableCRUD",
            "Effect": "Allow",
            "Action": [
                "dynamodb:PutItem",
                "dynamodb:GetItem",
                "dynamodb:UpdateItem",
                "dynamodb:DeleteItem",
                "dynamodb:Scan",
                "dynamodb:DescribeTable"
            ],
            "Resource": "arn:aws:dynamodb:AWS_REGION_PLACEHOLDER:AWS_ACCOUNT_ID_PLACEHOLDER:table/StudentRecords"
        }
    ]
}
```
5. Click **Next**.
6. Set **Policy name** to: `StudentRecordsDynamoDBPolicy`
7. Click **Create policy**.

### Step 11.2 — Create the EC2 IAM Role (Instance Profile)
1. In the IAM console left menu, click **Roles** &rarr; **Create role**.
2. **Trusted entity type:** Select **AWS service**.
3. **Service or use case:** Select **EC2**, then click **Next**.
4. On the **Add permissions** page, search for `StudentRecordsDynamoDBPolicy`, check the box next to it, and click **Next**.
5. Set **Role name** to: `StudentRecordsEC2Role`
6. Click **Create role**.

---

## 12. Security Group Configuration

1. Open the **Amazon EC2** console (**Services &rarr; Compute &rarr; EC2**).
2. In the left menu under **Network & Security**, click **Security Groups** &rarr; **Create security group**.
3. Configure basic details:
   - **Security group name:** `student-records-sg`
   - **Description:** `Allow HTTP 80 from anywhere and SSH 22 from admin IP`
   - **VPC:** Select your default VPC.
4. **Inbound rules** — Add these **two rules**:
   - **Rule 1 (Public Web Traffic):**
     - **Type:** `HTTP`
     - **Protocol:** `TCP`
     - **Port range:** `80`
     - **Source:** `Anywhere-IPv4` (`0.0.0.0/0`)
   - **Rule 2 (Admin SSH Access):**
     - **Type:** `SSH`
     - **Protocol:** `TCP`
     - **Port range:** `22`
     - **Source:** `My IP` *(restricts SSH access to your current public IP only)*
5. **Outbound rules:** Keep the default rule (`All traffic` to `0.0.0.0/0`) so the instance can install packages via `dnf`, clone from GitHub, and reach the DynamoDB endpoint.
6. Click **Create security group**.

> **Why Ports 5000 and 8000 Do NOT Need Public Access:**
> - Port `5000` is only used during local Windows development (`python app.py`).
> - On EC2, **Gunicorn** listens strictly on internal loopback (`127.0.0.1:8000`). **Nginx** listens on public port `80` and reverse-proxies requests to `127.0.0.1:8000`. Keeping port `8000` closed to the public internet prevents visitors from bypassing Nginx.
>
> **Subnet & Public IPv4 Requirement:**
> Because this practical architecture avoids a paid Application Load Balancer, your EC2 instance must be launched in a **public subnet** (a subnet with a route to an Internet Gateway) with **Auto-assign public IP** enabled so it receives a public IPv4 address reachable over HTTP port 80 and able to download packages from GitHub/AWS.

---

## 13. Launch Template Creation

### Step 13.1 — Prepare Your User Data Script Placeholders
Before creating the Launch Template, inspect `deploy/user_data.sh`. Near the top of the script, locate these two clearly marked variables:

```bash
REPO_URL="https://github.com/YOUR_USERNAME/cloud-student-records.git"
AWS_REGION="ap-south-1"
```

- Replace `YOUR_USERNAME` in `REPO_URL` with your actual GitHub username where you pushed the public `cloud-student-records` repository.
- Replace `ap-south-1` in `AWS_REGION` if you chose a different AWS region in Step 9.

### Step 13.2 — Create the EC2 Launch Template in AWS Console
1. In the **EC2 Console**, go to **Instances &rarr; Launch Templates** and click **Create launch template**.
2. **Launch template name and description:**
   - **Launch template name:** `student-records-launch-template`
   - **Template version description:** `v1 - AL2023 Flask Gunicorn Nginx DynamoDB`
   - **Auto Scaling guidance:** Check *"Provide guidance to help me set up a template that I can use with EC2 Auto Scaling"*.
3. **Application and OS Images (Amazon Machine Image):**
   - Click **Quick Start** &rarr; Select **Amazon Linux**.
   - Choose **Amazon Linux 2023 AMI** (64-bit x86, HVM).
4. **Instance type:**
   - Select **`t2.micro`** or **`t3.micro`** (Free Tier eligible depending on your AWS account region).
5. **Key pair (login):**
   - Select an existing key pair or click **Create new key pair** (Name: `student-records-key`, Type: `RSA`, Format: `.pem`), and download the `.pem` file safely.
6. **Network settings:**
   - **Subnet:** Select *"Don't include in launch template"* (the Auto Scaling Group will choose the public subnets).
   - **Firewall (security groups):** Select **Select existing security group** and choose **`student-records-sg`**.
   - Expand **Advanced network configuration**:
     - If a network interface isn't listed, click **Add network interface** (Device index `0`), select **`student-records-sg`**, and set **Auto-assign public IP** to **`Enable`**.
7. **Configure storage:** Leave default (`8 GiB gp3`).
8. **Advanced details** (expand at the bottom):
   - **IAM instance profile:** Select **`StudentRecordsEC2Role`**.
   - **Detailed CloudWatch monitoring:** Leave **Disabled** (Basic 5-minute monitoring is free and sufficient for this practical).
   - **User data:** Scroll to the bottom **User data** box and paste the entire contents of `deploy/user_data.sh` (with `REPO_URL` and `AWS_REGION` updated). Leave *"User data has already been base64 encoded"* **unchecked**.
9. Click **Create launch template**.
10. Open the created Launch Template details page and capture **Screenshot #8 (EC2 Launch Template)**.

---

## 14. Auto Scaling Group Creation

1. In the **EC2 Console**, scroll to the bottom of the left navigation pane and click **Auto Scaling Groups** &rarr; **Create Auto Scaling group**.
2. **Step 1 — Choose launch template or configuration:**
   - **Auto Scaling group name:** `student-records-asg`
   - **Launch template:** Select **`student-records-launch-template`** (Version: `Default (1)`).
   - Click **Next**.
3. **Step 2 — Choose instance launch options:**
   - **VPC:** Select your default VPC.
   - **Availability Zones and subnets:** Select at least **2 public subnets** (e.g., `ap-south-1a` and `ap-south-1b`).
   - Click **Next**.
4. **Step 3 — Configure advanced options:**
   - **Load balancing:** Select **No load balancer** (avoids unnecessary hourly ALB charges).
   - **Health checks:** Keep **EC2** health checks enabled, **Health check grace period:** `300` seconds.
   - Click **Next**.
5. **Step 4 — Configure group size and scaling:**
   - **Group size:**
     - **Desired capacity:** `1`
     - **Min desired capacity:** `1`
     - **Max desired capacity:** `2`
   - **Automatic scaling:** Select **Target tracking scaling policy**:
     - **Scaling policy name:** `cpu-target-50-policy`
     - **Metric type:** `Average CPU utilization`
     - **Target value:** `50`
     - **Instance warmup:** `180` seconds
   - Click **Next**.

   > **How Target-Tracking CloudWatch Alarms Work:**
   > When you create a target-tracking scaling policy in EC2 Auto Scaling, **AWS automatically creates and manages the corresponding CloudWatch alarms** (typically one High-CPU alarm to scale out when average CPU exceeds 50%, and one Low-CPU alarm to scale back in when CPU drops significantly below 50%). You do not need to create those scaling alarms manually.

6. **Step 5 & 6 — Notifications and Tags:**
   - Click **Next** on Notifications.
   - On **Add tags**, click **Add tag**:
     - **Key:** `Name`
     - **Value:** `student-records-ec2`
     - **Tag new instances:** Checked
   - Click **Next**.
7. **Step 7 — Review:**
   - Review all settings and click **Create Auto Scaling group**.
8. Capture **Screenshot #9 (Auto Scaling Group capacity)** and **Screenshot #10 (Automatic scaling policy & Activity history tab)**.

---

## 15. Public Website Testing & Verification

1. Go to **EC2 &rarr; Instances** and wait 1–2 minutes for the instance launched by `student-records-asg` to show:
   - **Instance state:** `Running`
   - **Status check:** `2/2 checks passed`
2. Capture **Screenshot #2 (EC2 instance in Running state)**.
3. Copy the instance's **Public IPv4 address** from the instance details pane.
4. Connect to the instance using **EC2 Instance Connect** (select instance &rarr; **Connect** &rarr; **EC2 Instance Connect** &rarr; **Connect**) or via SSH from PowerShell:
   ```powershell
   ssh -i path\to\student-records-key.pem ec2-user@<EC2_PUBLIC_IPV4>
   ```
5. Inside the EC2 Linux terminal, verify the deployment finished and services are active:
   ```bash
   sudo tail -n 30 /var/log/user-data.log
   sudo systemctl status student-app --no-pager
   sudo systemctl status nginx --no-pager
   curl -s http://127.0.0.1:8000/health && echo ""
   ```
6. Capture **Screenshot #3 (Connection/terminal showing application deployment)**.
7. Open your web browser and navigate to:
   ```text
   http://<EC2_PUBLIC_IPV4>
   ```
   *(Make sure to use `http://`, not `https://`.)*
8. Verify that the top header badge displays **`AWS Mode: Amazon DynamoDB`**.
9. Add 2–3 student records, test editing one record, and capture **Screenshot #4 (Application opened through the EC2-hosted endpoint)**.
10. Open **DynamoDB &rarr; Tables &rarr; `StudentRecords` &rarr; Explore table items** in the AWS Console to see your newly created items stored with UUID `student_id` keys. Capture **Screenshot #5 (DynamoDB table and sample items)**.

---

## 16. CloudWatch Graph and Alarm Verification

1. Open the **Amazon CloudWatch** console (**Services &rarr; Management & Governance &rarr; CloudWatch**).
2. **View the EC2 CPUUtilization Graph:**
   - In the left menu, click **Metrics &rarr; All metrics**.
   - Click **EC2** &rarr; **Per-Instance Metrics** (or **By Auto Scaling Group**).
   - Find your instance ID (or `student-records-asg`) and check the box next to **`CPUUtilization`**.
   - Set the time range at the top right to **`1h`**.
   - > **Note on Basic Monitoring:** Standard (free) EC2 monitoring sends metrics to CloudWatch at **5-minute intervals**. Wait 5–10 minutes after launching the instance and generating web traffic so data points appear on the chart. Paid Detailed Monitoring (1-minute intervals) is **not** required for this practical.
   - Capture **Screenshot #6 (CloudWatch metric graph)**.
3. **View the Scaling Alarm Configuration and State:**
   - In the left menu, click **Alarms &rarr; All alarms**.
   - You will see the two alarms automatically created by your Auto Scaling target-tracking policy (named `TargetTracking-student-records-asg-AlarmHigh-...` and `TargetTracking-student-records-asg-AlarmLow-...`).
   - Click on the **`AlarmHigh`** alarm to display its threshold graph (`CPUUtilization > 50`), state (`OK`, `In alarm`, or `Insufficient data`), and scaling action.
   - Capture **Screenshot #7 (CloudWatch alarm configuration/state)**.

---

## 17. Troubleshooting

### Useful Commands on the EC2 Instance (Amazon Linux 2023)
Run these commands inside your EC2 terminal to diagnose any deployment issues:

```bash
# 1. Watch or inspect the User Data bootstrap log
sudo cat /var/log/user-data.log

# 2. Check the status of the Gunicorn systemd service
sudo systemctl status student-app --no-pager

# 3. View recent application & Gunicorn logs (including DynamoDB errors)
sudo journalctl -u student-app -n 100 --no-pager

# 4. Restart the application service after any manual changes
sudo systemctl restart student-app

# 5. Check Nginx configuration and status
sudo nginx -t
sudo systemctl status nginx --no-pager
sudo tail -n 50 /var/log/nginx/error.log

# 6. Test internal Gunicorn and local Nginx endpoints directly
curl -i http://127.0.0.1:8000/health
curl -i http://127.0.0.1/health
```

### Common Issues & Fixes
| Symptom | Likely Cause | Fix |
| :--- | :--- | :--- |
| Browser hangs / times out on `http://<Public-IP>` | Security Group missing HTTP Port 80, or browser auto-redirected to `https://` | Verify `student-records-sg` allows Inbound HTTP TCP `80` from `0.0.0.0/0`, and explicitly type `http://` in the address bar. |
| `502 Bad Gateway` from Nginx | User Data is still installing packages, or `REPO_URL` placeholder wasn't updated | Wait 60 seconds and check `sudo cat /var/log/user-data.log` and `sudo systemctl status student-app`. |
| UI banner says *"Could not load/save student records from Amazon DynamoDB"* | Missing IAM Role, wrong table name, or wrong `AWS_REGION` | Confirm `StudentRecords` exists in the same region as `AWS_REGION`, and `StudentRecordsEC2Role` is attached to the EC2 instance. |

---

## 18. Cleanup of AWS Resources (Avoid Charges)

Once you have captured all **10 required screenshots** and verified your practical submission, delete the AWS resources in the following order so you do not incur ongoing charges:

1. **Delete the Auto Scaling Group (Terminates EC2 Instances Automatically):**
   - Go to **EC2 &rarr; Auto Scaling Groups**.
   - Select **`student-records-asg`** &rarr; Click **Delete** &rarr; Type `delete` to confirm.
   - *Note:* Deleting the Auto Scaling Group automatically terminates its running EC2 instances and deletes the target-tracking CloudWatch alarms. Wait 2–3 minutes and verify under **EC2 &rarr; Instances** that all instances are **`Terminated`**.
2. **Delete the EC2 Launch Template:**
   - Go to **EC2 &rarr; Launch Templates**.
   - Select **`student-records-launch-template`** &rarr; **Actions &rarr; Delete template** &rarr; Type `Delete` to confirm.
3. **Delete the DynamoDB Table:**
   - Go to **DynamoDB &rarr; Tables**.
   - Select **`StudentRecords`** &rarr; Click **Delete** &rarr; Uncheck *"Create a backup"* &rarr; Type `confirm` and click **Delete**.
4. **Delete the Security Group:**
   - Go to **EC2 &rarr; Security Groups**.
   - Select **`student-records-sg`** (after the EC2 instance is fully terminated) &rarr; **Actions &rarr; Delete security groups** &rarr; Click **Delete**.
5. **Delete the IAM Role and Custom Policy:**
   - Go to **IAM &rarr; Roles**, search for **`StudentRecordsEC2Role`**, select it, and click **Delete**.
   - Go to **IAM &rarr; Policies**, filter by **Customer managed**, select **`StudentRecordsDynamoDBPolicy`**, and click **Delete**.
6. **Delete the Key Pair (Optional):**
   - Go to **EC2 &rarr; Key Pairs**, select **`student-records-key`**, and delete it.
