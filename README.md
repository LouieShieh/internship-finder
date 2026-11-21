# internship-finder

A command-line tool that merges public internship lists into one daily shortlist for **F-1 international
students**. Roles you have already applied to are removed, and each role comes with two signals the lists
don't give you: whether the job description shuts out F-1 students, and whether the company has a record
of sponsoring H-1B visas.

一个命令行工具：把几个公开的实习列表合并成一份每天可用的候选清单，专门面向 **F-1 国际学生**。已经投过的岗位会被去掉。每个岗位还会多两条列表本身不提供的信息：JD 里有没有把 F-1 学生排除在外，以及这家公司过去有没有担保过 H-1B。

Python 3.11+, standard library only, no API keys.

需要 Python 3.11 及以上，只用标准库，不需要任何 API key。

```text
$ python3 -m internship_finder --check-jd 12 --grad-window 2028-12 2030-05
lists: Simplify 1344, vansh 2017, Speedy 851, Automated 910
kept 579 rows -> 418 distinct roles -> 418 on the shortlist
  dropped  2192: posted more than 14 days ago
  dropped   836: not a tech role for undergrads
  dropped   569: not in the US
  dropped   532: list says no sponsorship / citizens only
  dropped   414: company in exclusion list
H-1B data: USCIS H-1B approvals FY2022-FY2023 (65725 employers)
saved: output/shortlist_2026-11-20.csv
  2026-11-20 | Constellation Energy     | Powerfolio Data Analyst Intern                             |    H1B 25 | could not read the posting; open it yourself
  2026-11-20 | Lucid Motors             | AI/ML Intern - Vehicle Infotainment - Summer 2027          |           | ⚠ visa: not obligated to sponsor
  2026-11-20 | Daikin Comfort           | Data Analyst Intern                                        |     H1B 9 | ⚠ visa: not require sponsor | graduation years mentioned: 2027, 2029
  2026-11-20 | GTI Energy               | Data Science Intern                                        |           | no restriction wording found
  2026-11-20 | Mesirow                  | Software Developer Intern - IT                             |     H1B 1 | no restriction wording found | ⚠ graduation years mentioned: 2028
  ...
```

With `--applied your_applications.xlsx` it also prints how many roles were hidden as already applied, and why.

加上 `--applied 你的投递表.xlsx` 后，它还会列出有多少岗位因为已经投过被隐藏，以及隐藏的原因。

## Why / 为什么做这个

International students applying for internships run into the same problems again and again:

国际学生找实习时，总会反复遇到下面这些问题：

- **The lists overlap.** The same posting shows up on several lists under slightly different names
  ("Software Engineer Intern" vs. "Software Engineering Intern - Summer 2027"), sometimes with different
  company spellings.

  **列表之间大量重复。** 同一个岗位会出现在好几个列表里，职位名写法略有不同（"Software Engineer Intern" 和 "Software Engineering Intern - Summer 2027"），有时连公司名的拼法都不一样。
- **Most postings don't say whether they accept F-1 students.** The lists mark only a few roles as
  "no sponsorship". The rule is usually buried in the job description, as in "must be authorized to work
  now and in the future without sponsorship", or "OPT/CPT not eligible".

  **大多数岗位不说收不收 F-1。** 列表只给很少的岗位标了"不担保"，真正的限制通常写在 JD 正文里，比如 "must be authorized to work now and in the future without sponsorship"，或者 "OPT/CPT not eligible"。
- **Many career pages hide the text.** Job descriptions are loaded by JavaScript, so you have to open
  each one in a browser to find that sentence.

  **很多招聘页面不直接给正文。** JD 是用 JavaScript 加载的，要找那一句话，只能一个个在浏览器里打开看。
- **Tracking what you applied to is manual.** After a few hundred applications it is easy to apply to
  the same role twice, or to forget that you already have three applications at a company.

  **投递记录只能手动核对。** 投到几百个以后，很容易重复投同一个岗位，或者忘了自己在某家公司已经投了三个。

## What it does / 它做了什么

1. **Collects** open Summer internships from four public lists (see [Data sources](#data-sources--数据来源)).

   **收集**：从四个公开列表里取出仍在招的暑期实习（见[数据来源](#data-sources--数据来源)）。
2. **Filters** to US, recent, tech roles for undergraduates. It drops roles a list marks as "no
   sponsorship" or "citizens only", and companies on an exclusion list.

   **过滤**：只留下美国、最近发布、面向本科生的技术岗。列表标了"不担保"或"仅限公民"的岗位，以及排除表里的公司，都会去掉。
3. **Merges duplicates.** Two rows are one role if they share the company and title words, or link to
   the same posting (same job ID on Workday, Greenhouse, Lever, Ashby, ...). Short links are followed first.

   **合并重复**：公司相同且职位名关键词相同，或者链接指向同一个岗位（在 Workday、Greenhouse、Lever、Ashby 等系统上是同一个职位 ID），就算同一个岗位。短链接会先还原成真实地址。
4. **Removes roles you applied to**, using your own spreadsheet (CSV or Excel, read-only). A role counts
   as applied if:
   - it links to the same posting as one of your rows, or
   - its title is similar to one of yours at the same company.

   **去掉已投的岗位**：读你自己的投递表（CSV 或 Excel，只读）。满足以下任一条件，就算已经投过：
   - 链接和你表里某一行指向同一个岗位；
   - 同一家公司下，职位名和你投过的某个岗位相似。

   Companies where you already have `max_per_company` applications are hidden too. Company names are
   matched loosely, and also through the job-site account, so "ModMed" and "Modernizing Medicine" are one
   company when both link to `modmed.wd1.myworkdayjobs.com`.

   在某家公司已经投满 `max_per_company` 个的，这家公司也会被隐藏。公司名用宽松规则匹配，也会通过招聘系统里的公司账号匹配。所以 "ModMed" 和 "Modernizing Medicine" 只要都链接到 `modmed.wd1.myworkdayjobs.com`，就算同一家公司。
5. **Adds H-1B history**: the number of H-1B petitions USCIS approved for the company.

   **补充 H-1B 记录**：USCIS 为这家公司批准过多少份 H-1B 申请。
6. **Ranks** the list:
   1. programs for first- and second-year students (Google STEP, Microsoft Explore, ...);
   2. companies you haven't applied to yet;
   3. newest postings.

   **排序**：
   1. 面向大一、大二的项目排最前（Google STEP、Microsoft Explore 等）；
   2. 其次是还没投过的公司；
   3. 最后按发布时间，新的在前。
7. **Optionally reads the top N job descriptions** (`--check-jd N`) and flags restrictive wording (see
   [Job description check](#job-description-check--jd-检查)).

   **可选：读前 N 个岗位的 JD**（`--check-jd N`），标出限制性的措辞（见 [JD 检查](#job-description-check--jd-检查)）。
8. **Writes** `output/shortlist_<date>.csv`, which opens directly in Excel, and prints the top rows.

   **输出**：写出 `output/shortlist_<日期>.csv`，可以直接用 Excel 打开，同时在终端打印排在最前的几行。

## Quick start / 快速开始

```bash
git clone https://github.com/LouieShieh/internship-finder.git
cd internship-finder
python3 -m internship_finder                     # roles posted in the last 14 days / 最近 14 天发布的岗位
python3 -m internship_finder --days 7 --check-jd 20
python3 -m internship_finder --applied ~/Documents/applications.xlsx --grad-window 2028-12 2030-05
```

To keep your settings, copy `config.example.toml` to `config.toml` and edit it. Git ignores `config.toml`,
so your file paths stay out of the repository. To get an `internship-finder` command, run `pip install -e .`
(optional).

想保存自己的设置，就把 `config.example.toml` 复制成 `config.toml` 再改。git 会忽略 `config.toml`，所以你的文件路径不会进仓库。想要一个 `internship-finder` 命令，可以运行 `pip install -e .`（可选）。

### Your applications file / 你的投递表

Any CSV or Excel sheet with a company column and a title column works; a link column is optional but
makes matching much more reliable. Columns are found from the header text ("Company" / "Organization",
"Title" / "Position" / "Role", "URL" / "Link"). If the tool can't find them, set them in `config.toml`.
This example is for a tracker template with its header on row 5 and a sample row on row 6:

任何有"公司"列和"职位"列的 CSV 或 Excel 表都能用。"链接"列可以没有，但有了会匹配得准得多。程序按表头文字找列（"Company" / "Organization"、"Title" / "Position" / "Role"、"URL" / "Link"）；找不到的话，可以在 `config.toml` 里指定。下面的例子对应一种表头在第 5 行、第 6 行是示例的投递表模板：

```toml
[applied]
path = "~/Documents/applications.xlsx"
sheet = "Tracker"
first_data_row = 7
# columns = { company = "D", title = "E", url = "F" }
```

The file is opened read-only and never modified.

文件只会以只读方式打开，永远不会被修改。

## Output columns / 输出列

| Column 列 | Meaning 含义 |
|---|---|
| `underclass` | `yes` for programs aimed at first- and second-year students<br>面向大一、大二的项目标 `yes` |
| `company`, `title`, `locations`, `posted`, `salary` | From the lists. `posted` is the earliest date any list gives<br>来自列表。`posted` 取各列表里最早的日期 |
| `h1b_approvals` | H-1B petitions USCIS approved for this employer in the loaded years. Blank means no name match, not zero<br>已加载年份里 USCIS 为这家雇主批准的 H-1B 数量。空白表示名字没匹配上，不等于零 |
| `h1b_employer` | The legal name that matched, so you can check it ("+N more" when several entities were summed)<br>匹配到的法定公司名，方便核对（多个实体加总时显示 "+N more"） |
| `list_sponsorship` | `offers` if a list marks the role as offering sponsorship<br>列表标了"提供担保"的显示 `offers` |
| `applied_at_company` | How many of your applications are at this company<br>你在这家公司已经投了几个 |
| `jd_check` | Result of the job description check (with `--check-jd`)<br>JD 检查结果（需要 `--check-jd`） |
| `sources` | Which lists carry the role<br>哪些列表收录了这个岗位 |
| `url` | The application link (a direct job-site link when any list has one)<br>投递链接（只要有列表给了招聘系统的直链，就优先用直链） |

## Job description check / JD 检查

`--check-jd N` reads the top N postings, 8 at a time, and reports each kind of restriction it finds, with
the words that matched:

`--check-jd N` 会读排在前面的 N 个岗位（每次并行读 8 个），把找到的每一类限制连同匹配到的原文一起列出来：

| Flag 标记 | Examples of what it catches 能抓到的例子 |
|---|---|
| `visa` | "unable to sponsor", "without sponsorship now or in the future", "OPT/CPT not eligible", "unrestricted work authorization"<br>签证：不担保、现在和将来都不需要担保、OPT/CPT 不符合条件、要求不受限的工作许可 |
| `citizenship/clearance` | "must be a U.S. citizen", "ability to obtain a security clearance"<br>公民身份 / 安全许可：必须是美国公民、能拿到安全许可 |
| `U.S. person/export control` | "U.S. person", ITAR, export licenses. These matter for some nationalities, so read the wording<br>U.S. Person / 出口管制：U.S. person、ITAR、出口许可。对部分国籍有影响，要读原文 |
| `class year` | "rising seniors", "junior or senior standing", "final-year students"<br>年级：只招升大四、要求大三或大四、毕业年级学生 |
| `part-time/term-time` | part-time, year-round, "during the school year", 10–29 hours a week. F-1 students generally can't work off campus during the term<br>兼职 / 学期中：兼职、全年、学期中工作、每周 10–29 小时。F-1 学生学期中一般不能在校外工作 |
| graduation years | Years mentioned near "graduating" / "class of". With `--grad-window`, a ⚠ means the posting's range leaves you out, for example "graduating by June 2028" when you graduate in December 2028<br>毕业年份："graduating" / "class of" 附近出现的年份。设置了 `--grad-window` 时，⚠ 表示岗位要求的毕业时间不包括你，比如岗位写 "graduating by June 2028"，而你 2028 年 12 月毕业 |

Application-form questions such as "Will you now or in the future require sponsorship? Yes / No" are
recognized and not counted as rules.

像 "Will you now or in the future require sponsorship? Yes / No" 这种申请表里的问题，程序能认出来，不会当成限制条件。

Most career sites render the description with JavaScript, so the tool reads the job site's own public
posting API where there is one:

大多数招聘网站用 JavaScript 显示 JD，所以只要招聘系统有公开的职位接口，程序就直接从接口读：

- Workday
- Greenhouse
- Lever
- Ashby
- SmartRecruiters
- Oracle Recruiting Cloud
- Eightfold
- iCIMS
- UKG (UltiPro)
- BambooHR

Other sites fall back to the page HTML. "could not read the posting" means the site didn't give the text
to a script, so open it yourself.

其他网站退回到读网页 HTML。显示 "could not read the posting"，说明网站没有把正文给脚本，需要你自己打开看。

**This is a keyword search, not a verdict.** "no restriction wording found" does not mean a company
accepts F-1 students. Read the posting, and ask your school's international student office about CPT
before you accept an offer.

**这只是关键词搜索，不是结论。** "no restriction wording found" 不代表公司接受 F-1 学生。投之前请读原文，接 offer 之前请向学校的国际学生办公室确认 CPT。

## H-1B data / H-1B 数据

The H-1B counts come from the USCIS [H-1B Employer Data Hub](https://www.uscis.gov/tools/reports-and-studies/h-1b-employer-data-hub):
the number of initial and continuing petitions approved per employer. A company that has never sponsored
an H-1B is less likely to take F-1 interns it can't convert to full time. That makes the count a useful
hint, but not a rule: internships on CPT don't need sponsorship at all.

H-1B 数量来自 USCIS 的 [H-1B Employer Data Hub](https://www.uscis.gov/tools/reports-and-studies/h-1b-employer-data-hub)，即每家雇主获批的首次和续签申请数。从没担保过 H-1B 的公司，不太愿意招以后没法转全职的 F-1 实习生，所以这个数字是一个有用的参考，但不是规则：用 CPT 做实习本身完全不需要担保。

- **What gets downloaded.** By default the tool downloads the archived per-year exports (FY2022 and FY2023,
  about 6 MB) once and caches them in `.cache/`. FY2023 is a partial year.

  **会下载什么。** 默认只下载一次 USCIS 存档的年度数据（FY2022 和 FY2023，约 6 MB），缓存在 `.cache/`。FY2023 只有部分年份的数据。
- **Newer years.** Data through FY2026 is only in the interactive hub. To add it:
  1. Open the hub's **Crosstab** view.
  2. Choose **Download**, then **CSV**.
  3. Pass the file with `--h1b-csv FILE` or list it under `[h1b] csv` in `config.toml`.

  **更新的年份。** 到 FY2026 的数据只能在交互式数据中心里拿，步骤：
  1. 打开数据中心的 **Crosstab** 视图；
  2. 选 **Download**，再选 **CSV**；
  3. 用 `--h1b-csv 文件` 传进来，或者写在 `config.toml` 的 `[h1b] csv` 里。

  The parser looks for an "Employer" column and sums every "Approval" column. It has been tested on the
  archived format and on UTF-16, tab-separated crosstab files, so check that the numbers look right the
  first time you use a new export.

  解析时找 "Employer" 列，并把所有 "Approval" 列加起来。测试过存档格式和 UTF-16、制表符分隔的 crosstab 文件。第一次用新导出的文件时，请检查一下数字对不对。
- **How names are matched.** Names are normalized, then matched exactly or as a whole-word prefix
  ("Amazon" → "AMAZON.COM SERVICES LLC", "AMAZON WEB SERVICES INC", ...). Names shorter than four letters
  must match exactly. Check `h1b_employer` before relying on a number.

  **名字怎么匹配。** 先把名字规范化，再按完全一致或整词前缀匹配（"Amazon" → "AMAZON.COM SERVICES LLC"、"AMAZON WEB SERVICES INC" 等）。少于四个字母的名字必须完全一致。用这个数字之前，先看一下 `h1b_employer`。

## Data sources / 数据来源

| List 列表 | What it adds 提供什么 |
|---|---|
| [SimplifyJobs/Summer2027-Internships](https://github.com/SimplifyJobs/Summer2027-Internships) | The largest hand-curated list (`listings.json`)<br>规模最大的人工整理列表（`listings.json`） |
| [vanshb03/Summer2027-Internships](https://github.com/vanshb03/Summer2027-Internships) | Marks many more roles as "no sponsorship" / "citizens only"<br>标"不担保"/"仅限公民"的岗位多得多 |
| [speedyapply/2027-SWE-College-Jobs](https://github.com/speedyapply/2027-SWE-College-Jobs) | Includes salaries for many roles<br>很多岗位带薪资 |
| [zshah101/Automated-List-Of-Summer-2027-and-Fall-2026-Tech-Internships](https://github.com/zshah101/Automated-List-Of-Summer-2027-and-Fall-2026-Tech-Internships) | Reads employer job boards directly, so it finds roles the curated lists haven't added (in November 2026, about 290 US tech internships for Summer 2027 that none of the other three listed)<br>直接读公司自己的招聘系统，能找到人工列表还没收录的岗位（2026 年 11 月，约有 290 个美国 2027 暑期技术实习是另外三个列表都没有的） |

The lists are downloaded when the tool runs and are not redistributed; each belongs to its maintainers.
For another year, pass `--year 2028`. The first three lists follow a yearly naming pattern. The automated
list's URL is set per cycle in `internship_finder/sources.py`, or you can override it with
`[search] source_urls`.

列表在运行时下载，本仓库不转发这些数据，它们归各自的维护者所有。换年份用 `--year 2028`：前三个列表每年按固定规则命名，自动列表的地址按招聘季写在 `internship_finder/sources.py` 里，也可以用 `[search] source_urls` 覆盖。

**Etiquette.** The tool only reads public lists and the public posting APIs that job sites provide for
career pages. It identifies itself with a `User-Agent` of `internship-finder/<version>`. It doesn't log in
anywhere, doesn't scrape LinkedIn or Indeed (their terms forbid it), and caches what it can (short links,
H-1B files).

**使用规范。** 程序只读公开列表，以及招聘系统为招聘页面提供的公开职位接口。请求时如实标明身份，`User-Agent` 为 `internship-finder/<版本号>`。它不登录任何网站，不爬 LinkedIn 或 Indeed（它们的条款禁止爬取），能缓存的都会缓存（短链接、H-1B 文件）。

## Exclusion list / 排除表

`internship_finder/data/excluded_companies.txt` lists companies whose internship postings say they won't
consider F-1 students, with the date each was checked. Policies change and can differ between teams, so:

`internship_finder/data/excluded_companies.txt` 列出了在实习 JD 里明确表示不考虑 F-1 学生的公司，每条都注明了核查日期。公司政策会变，不同团队也可能不一样，所以：

- to keep your own list, add it with `[filters] exclude_files`;

  想用自己的排除表，用 `[filters] exclude_files` 加进来；
- to turn the bundled list off, use `--no-default-exclusions`;

  不想用内置的排除表，加 `--no-default-exclusions`；
- if an entry is wrong, open an issue.

  发现哪条不对，欢迎提 issue。

## Development / 开发

```bash
python3 -m unittest discover -s tests -v    # offline; about 60 tests / 离线运行，约 60 个测试
```

| Module 模块 | Responsibility 职责 |
|---|---|
| `sources.py` | Download and parse each list into `Listing` records<br>下载并解析每个列表，转成 `Listing` 记录 |
| `filters.py` | Tech-title, underclass-program and exclusion-list rules<br>技术岗判断、低年级项目识别、排除表规则 |
| `normalize.py` | Company keys, title tokens, US locations<br>公司名归一化、职位名关键词、美国地点判断 |
| `links.py` | Job-site link patterns (posting ID + company account), short-link resolution with cache<br>招聘系统链接规则（职位 ID + 公司账号），带缓存的短链接还原 |
| `applied.py` | Read your CSV/XLSX (standard-library XLSX reader) and match roles against it<br>读你的 CSV/XLSX（用标准库实现的 XLSX 读取），判断岗位是否已投 |
| `pipeline.py` | Filter → merge → compare with applications → H-1B → sort (pure functions)<br>过滤 → 合并 → 对比已投 → H-1B → 排序（都是纯函数） |
| `jd.py` | Read posting text through job-site APIs, flag restrictions, check graduation years<br>通过招聘系统接口读 JD，标出限制，检查毕业年份 |
| `h1b.py` | Parse USCIS exports and match company names to employers<br>解析 USCIS 数据，把公司名匹配到雇主 |
| `config.py`, `cli.py` | Settings (defaults → `config.toml` → flags) and the command line<br>配置（默认值 → `config.toml` → 命令行参数）和命令行入口 |

## Limitations / 局限

- **Keyword checks miss things.** They can miss rules written in unusual ways and can flag harmless
  sentences. Always read the posting.

  **关键词检查会漏。** 写法特别的限制可能抓不到，无害的句子也可能被误标。一定要读原文。
- **Company-name matching is heuristic.** That applies to both the exclusion list and the H-1B data.

  **公司名匹配是启发式的。** 排除表和 H-1B 数据都是这样。
- **List dates vary.** `posted` is when a list first showed the role, which isn't always when the company
  posted it.

  **列表的日期不一定准。** `posted` 是列表最早收录这个岗位的日期，不一定是公司真正发布的日期。
- **Not legal advice.** Work authorization rules (CPT, OPT, export control) depend on your situation;
  your school's international student office has the final word.

  **不构成法律建议。** 工作许可的规则（CPT、OPT、出口管制）因人而异，以学校国际学生办公室的答复为准。

## License / 许可证

MIT
