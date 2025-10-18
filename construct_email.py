from paper import ArxivPaper
import math
from tqdm import tqdm
from email.header import Header
from email.mime.text import MIMEText
from email.utils import parseaddr, formataddr
import smtplib
import datetime
import time
from loguru import logger

framework = """
<!DOCTYPE HTML>
<html>
<head>
  <style>
    .star-wrapper {
      font-size: 1.3em; /* 调整星星大小 */
      line-height: 1; /* 确保垂直对齐 */
      display: inline-flex;
      align-items: center; /* 保持对齐 */
    }
    .half-star {
      display: inline-block;
      width: 0.5em; /* 半颗星的宽度 */
      overflow: hidden;
      white-space: nowrap;
      vertical-align: middle;
    }
    .full-star {
      vertical-align: middle;
    }
  </style>
</head>
<body>

<div>
    __CONTENT__
</div>

<br><br>
<div>
To unsubscribe, remove your email in your Github Action setting.
</div>

</body>
</html>
"""

def get_empty_html():
  block_template = """
  <table border="0" cellpadding="0" cellspacing="0" width="100%" style="font-family: Arial, sans-serif; border: 1px solid #ddd; border-radius: 8px; padding: 16px; background-color: #f9f9f9;">
  <tr>
    <td style="font-size: 20px; font-weight: bold; color: #333;">
        No Papers Today. Take a Rest!
    </td>
  </tr>
  </table>
  """
  return block_template

def get_block_html(title:str, authors:str, rate:str, arxiv_id:str, article:str, entry_id:str, code_url:str=None, paper_type=None):
    code = f'<a href="{code_url}" style="display: inline-block; text-decoration: none; font-size: 14px; font-weight: bold; color: #fff; background-color: #5bc0de; padding: 8px 16px; border-radius: 4px; margin-left: 8px;">Code</a>' if code_url else ''

    # 根据论文类型设置标签和颜色
    type_label = ""
    type_color = "#5bc0de"  # 默认蓝色
    if paper_type == "solution":
        type_label = '<span style="display: inline-block; padding: 4px 8px; background-color: #28a745; color: white; font-size: 12px; font-weight: bold; border-radius: 3px; margin-left: 8px;">解决方案型</span>'
        type_color = "#28a745"  # 绿色
    elif paper_type == "exploratory":
        type_label = '<span style="display: inline-block; padding: 4px 8px; background-color: #fd7e14; color: white; font-size: 12px; font-weight: bold; border-radius: 3px; margin-left: 8px;">探究型</span>'
        type_color = "#fd7e14"  # 橙色

    # 处理结构化摘要格式
    formatted_article = article
    if "**现有方案的缺点**" in article or "**探究的问题**" in article:
        # 新的结构化格式，转换为HTML
        formatted_article = article.replace("**现有方案的缺点**", '<strong style="color: #dc3545; font-size: 16px;">⚠️ 现有方案的缺点</strong>')
        formatted_article = formatted_article.replace("**新方案的设计理念**", '<strong style="color: #007bff; font-size: 16px;">💡 新方案的设计理念</strong>')
        formatted_article = formatted_article.replace("**新方案的实现方式**", '<strong style="color: #28a745; font-size: 16px;">🔧 新方案的实现方式</strong>')
        formatted_article = formatted_article.replace("**探究的问题**", '<strong style="color: #fd7e14; font-size: 16px;">🔍 探究的问题</strong>')
        formatted_article = formatted_article.replace("**实验结论**", '<strong style="color: #6f42c1; font-size: 16px;">📊 实验结论</strong>')
        # 将换行符转换为HTML换行
        formatted_article = formatted_article.replace('\n\n', '<br><br>')
        formatted_article = formatted_article.replace('\n', '<br>')

    block_template = """
    <table border="0" cellpadding="0" cellspacing="0" width="100%" style="font-family: Arial, sans-serif; border: 1px solid #ddd; border-radius: 8px; padding: 16px; background-color: #f9f9f9; margin-bottom: 16px;">
    <tr>
        <td style="font-size: 20px; font-weight: bold; color: #333; padding-bottom: 8px;">
            {title}{type_label}
        </td>
    </tr>
    <tr>
        <td style="font-size: 14px; color: #666; padding: 4px 0;">
            <strong>Authors:</strong> {authors}
        </td>
    </tr>
    <tr>
        <td style="font-size: 14px; color: #333; padding: 8px 0;">
            <strong>Relevance:</strong> {rate} &nbsp;&nbsp;&nbsp; <strong>arXiv ID:</strong> {arxiv_id}
        </td>
    </tr>
    <tr>
        <td style="font-size: 14px; color: #555; padding: 12px 0; line-height: 1.6; border-top: 1px solid #eee; border-bottom: 1px solid #eee; margin: 8px 0;">
            <div style="background-color: #fff; padding: 12px; border-radius: 4px; border-left: 4px solid {type_color};">
                <strong style="color: #333; font-size: 15px;">📄 Paper Analysis</strong>
                <div style="margin-top: 8px; text-align: justify;">
                    {formatted_article}
                </div>
            </div>
        </td>
    </tr>

    <tr>
        <td style="padding: 12px 0;">
            <a href="{entry_id}" style="display: inline-block; text-decoration: none; font-size: 14px; font-weight: bold; color: #fff; background-color: #d9534f; padding: 10px 20px; border-radius: 4px;">📄 Read PDF</a>
            {code}
        </td>
    </tr>
</table>
"""
    return block_template.format(
        title=title,
        authors=authors,
        rate=rate,
        arxiv_id=arxiv_id,
        article=article,
        formatted_article=formatted_article,
        entry_id=entry_id,
        code=code,
        type_label=type_label,
        type_color=type_color
    )

def get_stars(score:float):
    full_star = '<span class="full-star">⭐</span>'
    half_star = '<span class="half-star">⭐</span>'
    low = 6
    high = 8
    if score <= low:
        return ''
    elif score >= high:
        return full_star * 5
    else:
        interval = (high-low) / 10
        star_num = math.ceil((score-low) / interval)
        full_star_num = int(star_num/2)
        half_star_num = star_num - full_star_num * 2
        return '<div class="star-wrapper">'+full_star * full_star_num + half_star * half_star_num + '</div>'


def render_email(papers:list[ArxivPaper]):
    parts = []
    if len(papers) == 0 :
        return framework.replace('__CONTENT__', get_empty_html())
    
    for p in tqdm(papers,desc='Rendering Email'):
        rate = get_stars(p.score)
        authors = [a.name for a in p.authors[:5]]
        authors = ', '.join(authors)
        if len(p.authors) > 5:
            authors += ', ...'

        # 获取论文类型，确保向后兼容
        paper_type_value = None
        try:
            if hasattr(p, 'paper_type') and p.paper_type:
                paper_type_value = p.paper_type.value
        except Exception as e:
            logger.warning(f"Error getting paper type for {p.arxiv_id}: {e}")

        parts.append(get_block_html(p.title, authors, rate, p.arxiv_id, p.article, p.entry_id, p.code_url, paper_type_value))
        time.sleep(10)

    content = '<br>' + '</br><br>'.join(parts) + '</br>'
    return framework.replace('__CONTENT__', content)

def send_email(sender:str, receiver:str, password:str,smtp_server:str,smtp_port:int, html:str,):
    def _format_addr(s):
        name, addr = parseaddr(s)
        return formataddr((Header(name, 'utf-8').encode(), addr))

    msg = MIMEText(html, 'html', 'utf-8')
    msg['From'] = _format_addr('Arxiv Daily <%s>' % sender)
    msg['To'] = _format_addr('You <%s>' % receiver)
    today = datetime.datetime.now().strftime('%Y/%m/%d')
    msg['Subject'] = Header(f'Daily arXiv {today}', 'utf-8').encode()

    try:
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
    except Exception as e:
        logger.warning(f"Failed to use TLS. {e}")
        logger.warning(f"Try to use SSL.")
        server = smtplib.SMTP_SSL(smtp_server, smtp_port)

    server.login(sender, password)
    server.sendmail(sender, [receiver], msg.as_string())
    server.quit()
