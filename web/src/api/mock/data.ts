import dayjs from 'dayjs'
import type { User, Post, Comment, NotificationItem, HotSearch } from '@/types'

const ago = (n: number, unit: dayjs.ManipulateType) => dayjs().subtract(n, unit).toISOString()

export const mockUsers: User[] = [
  { id: 1, username: '夜班书虫', email: 'reader@sayer.app', bio: '白天搬砖，晚上追更。书架 300+，完本不足 30。', follower_count: 328, following_count: 120, post_count: 45, created_at: ago(420, 'day') },
  { id: 2, username: '日更三千', bio: '全职写手，人生目标是不断更。', follower_count: 1204, following_count: 98, post_count: 231, created_at: ago(800, 'day') },
  { id: 3, username: '毒舌推书君', bio: '只推仙草，毒药直接埋。', follower_count: 8930, following_count: 210, post_count: 512, created_at: ago(1200, 'day') },
  { id: 4, username: '设定控不打烊', bio: '考据党，正在给一本架空小说画世界地图。', follower_count: 445, following_count: 301, post_count: 88, created_at: ago(300, 'day') },
  { id: 5, username: '咸鱼编辑', bio: '某站签约编辑，收稿收到手软。', follower_count: 2150, following_count: 167, post_count: 176, created_at: ago(900, 'day') },
  { id: 6, username: '咕咕咕咕', bio: '作者。主业咕咕，副业更新。', follower_count: 189, following_count: 256, post_count: 34, created_at: ago(150, 'day') },
  { id: 7, username: '本章说十级学者', bio: '不看本章说等于白看。', follower_count: 567, following_count: 432, post_count: 203, created_at: ago(600, 'day') },
  { id: 8, username: '漫剧观察员', bio: '关注 AI 漫剧改编的一切风吹草动。', follower_count: 3300, following_count: 88, post_count: 145, created_at: ago(1000, 'day') },
]

export const mockPosts: Post[] = [
  { id: 1, user_id: 3, username: '毒舌推书君', content: '【推书】《玄鉴仙族》，评级：仙草。\n\n家族流修仙的集大成者。没有降智反派，没有强行热血，一个家族七百年的起承转合，写得像族谱一样扎实。\n\n毒点预警：前期慢热，主角三百章才出山。但熬过去就是琼楼玉宇。\n\n适合人群：看腻了秒天秒地的老书虫。', image_url: null, like_count: 892, comment_count: 94, created_at: ago(2, 'hour') },
  { id: 2, user_id: 2, username: '日更三千', content: '全勤打卡第 187 天。\n\n今天写到主角身世揭底，自己先哭了半小时。读者以为作者是发刀的，其实作者是第一个挨刀的。\n\n晚上八点还有一更，别催，在写了。', image_url: null, like_count: 1204, comment_count: 217, created_at: ago(5, 'hour') },
  { id: 3, user_id: 4, username: '设定控不打烊', content: '忍不了了，挂一本最近很火的玄幻。\n\n第 80 章：主角越三级挑战，九死一生。\n第 800 章：主角越三个大境界，一拳秒了。\n\n战力膨胀不是问题，问题是作者把"代价"写没了。没有代价的力量体系，和开挂模拟器有什么区别？', image_url: null, like_count: 667, comment_count: 158, created_at: ago(9, 'hour') },
  { id: 4, user_id: 1, username: '夜班书虫', content: '追了三年的书今天完结了。\n\n最后一章停在"他回头看了一眼来路，雪落满肩"。\n\n关掉手机在阳台站了很久。好书完结像搬家，你知道东西都在，但就是空了点什么。', image_url: null, like_count: 756, comment_count: 123, created_at: ago(14, 'hour') },
  { id: 5, user_id: 8, username: '漫剧观察员', content: '重磅：又有两部头部网文官宣 AI 漫剧改编，一部仙侠一部都市。\n\n看了预告片，说实话超出预期——打斗分镜已经能看了，人物一致性还差口气。\n\n照这个速度，"今天完结，明天出漫剧"可能真的不是段子。这个行业要变天了，各位作者朋友怎么看？', image_url: 'https://picsum.photos/seed/aimanga/640/400', like_count: 943, comment_count: 186, created_at: ago(1, 'day') },
  { id: 6, user_id: 6, username: '咕咕咕咕', content: '【请假条】\n\n今日无更。理由：卡文。\n\n具体症状：打开文档两小时，写了删删了写，净增量负三百字。\n\n明天双更补上。如果没补，当我没说。', image_url: null, like_count: 421, comment_count: 287, created_at: ago(1, 'day') },
  { id: 7, user_id: 7, username: '本章说十级学者', content: '今日最佳本章说：\n\n原文："他握紧了手中的剑。"\n本章说："他握紧了手中的见，因为见得多了。"\n\n哈哈哈哈哈哈谁懂啊，本章说才是本体，正文只是评论区引子。', image_url: null, like_count: 1536, comment_count: 342, created_at: ago(2, 'day') },
  { id: 8, user_id: 5, username: '咸鱼编辑', content: '审稿十年，说点得罪人的：黄金三章不是玄学，是有公式的。\n\n第一章出核心矛盾，第二章出金手指，第三章出第一个小高潮。主角三页之内必须"想要点什么"。\n\n做不到这三条的书，签约率不足一成。稿子堆里的白骨都是这么来的。', image_url: null, like_count: 2103, comment_count: 341, created_at: ago(2, 'day') },
  { id: 9, user_id: 4, username: '设定控不打烊', content: '给我正在考据的那本架空文画的势力地图，整理到第三版了。\n\n作者自己估计都没想到，有读者会给他算各州府的粮食产量能不能支撑那场战争。\n\n结论：支撑不了。第三章那场围城战是个 bug。', image_url: 'https://picsum.photos/seed/fantasymap/640/430', like_count: 588, comment_count: 92, created_at: ago(3, 'day') },
  { id: 10, user_id: 1, username: '夜班书虫', content: '深夜破防时刻：\n\n追了八百章的悬疑文，凶手是主角的猫。\n\n不是比喻，不是人格分裂，是真的猫。\n\n我图什么啊我。', image_url: null, like_count: 1893, comment_count: 264, created_at: ago(3, 'day') },
  { id: 11, user_id: 2, username: '日更三千', content: '新书上架首日，首订破三千，超出预期一倍。\n\n感谢每一位付费的读者。网文这行，正版读者就是作者的衣食父母，这话一点不夸张。\n\n今晚加更，三章。', image_url: null, like_count: 1567, comment_count: 289, created_at: ago(4, 'day') },
  { id: 12, user_id: 3, username: '毒舌推书君', content: '【避雷】本周扫了十五本新书，埋了十四本。\n\n共性毒点：主角刚出场就人厌狗嫌，作者还以为这叫"废柴流"。\n\n废柴流的核心是"所有人都看走眼了"，不是"所有人都没看走眼"。望周知。', image_url: null, like_count: 1104, comment_count: 156, created_at: ago(4, 'day') },
  { id: 13, user_id: 6, username: '咕咕咕咕', content: '读者群里有人给我的书写了一篇三千字的长评，逐章分析我埋的暗线。\n\n比我自己的大纲都完整。\n\n不敢说话，怕暴露我后面还没想好。', image_url: null, like_count: 2341, comment_count: 412, created_at: ago(5, 'day') },
  { id: 14, user_id: 7, username: '本章说十级学者', content: '发现一个规律：一本都市文的精彩程度，和本章说里"报备"浓度成正比。\n\n"睡前最后亿章"\n"看到这里的都是兄弟"\n"三点了，明天还要上班"\n\n大家都是一边喊着睡觉一边通宵的人。', image_url: null, like_count: 876, comment_count: 129, created_at: ago(5, 'day') },
  { id: 15, user_id: 8, username: '漫剧观察员', content: '整理了一份「已改编 / 改编中网文漫剧清单」，含播出平台和更新进度，一共 47 部。\n\n评论区自取。有遗漏的欢迎补充，我持续更新。', image_url: null, like_count: 823, comment_count: 312, created_at: ago(6, 'day') },
  { id: 16, user_id: 5, username: '咸鱼编辑', content: '今天收到一份投稿，开篇第一句：\n\n"他死的那天，全城都在庆祝。"\n\n就这一句，我直接把全文看完了。好的开头不解释世界，只制造问题。', image_url: null, like_count: 1456, comment_count: 187, created_at: ago(7, 'day') },
  { id: 17, user_id: 4, username: '设定控不打烊', content: '考据冷知识：仙侠文里人手一个的"储物戒指"，最早大规模流行是因为作者们不想描写主角搬家。\n\n一个设定解决所有后勤描写，堪称网文史上最伟大的偷懒发明。', image_url: null, like_count: 734, comment_count: 96, created_at: ago(8, 'day') },
  { id: 18, user_id: 1, username: '夜班书虫', content: '书荒了，来交换书单。\n\n我的口味：慢热、群像、有始有终，拒绝无脑爽。\n\n最近的三本命：《玄鉴仙族》《道诡异仙》《我的治愈系游戏》。\n\n你留一本，我回一本。', image_url: null, like_count: 645, comment_count: 428, created_at: ago(9, 'day') },
  { id: 19, user_id: 3, username: '毒舌推书君', content: '一句话书评挑战，今天毒舌三本的：\n\n《XX赘婿》：开局一个碗，结局一个国。\n《XX复苏》：鬼比人讲道理。\n《XX小铺》：流水账写到极致就是生活流。\n\n想被点评的，评论区报名字。', image_url: null, like_count: 1123, comment_count: 356, created_at: ago(10, 'day') },
  { id: 20, user_id: 6, username: '咕咕咕咕', content: '重大通知：\n\n本咕这次真的要日更了。\n\n合同签了，全勤拿了，退路断了。\n\n望各位监督。此帖为证。', image_url: null, like_count: 1789, comment_count: 445, created_at: ago(11, 'day') },
  { id: 21, user_id: 2, username: '日更三千', content: '写打斗卡住了，去楼下看小孩打水仗。\n\n回来一口气写了六千字。原来最好的动作指导是七岁男孩。', image_url: null, like_count: 689, comment_count: 72, created_at: ago(12, 'day') },
  { id: 22, user_id: 8, username: '漫剧观察员', content: 'AI 漫剧评论区现状：\n\n原著党："改得面目全非！小说里这段心理描写封神了！"\n路人党："挺好看的啊。"\n\n每次改编都是这个剧本。说真的，文字的张力和画面的张力本来就是两回事，心理戏封神恰恰是因为它是文字。', image_url: null, like_count: 934, comment_count: 203, created_at: ago(13, 'day') },
  { id: 23, user_id: 7, username: '本章说十级学者', content: '血泪教训：不要在图书馆看沙雕文。\n\n憋笑憋到发抖，对面考研的兄弟看我的眼神像在看病情通报。', image_url: null, like_count: 1267, comment_count: 178, created_at: ago(14, 'day') },
  { id: 24, user_id: 5, username: '咸鱼编辑', content: '月底了，这个月的签约数据出来：投稿 2147 份，签约 63 份。\n\n没签上的朋友别灰心，我当年也是作者，抽屉里至今锁着三本没签约的书。\n\n它们不丢人，它们是路。', image_url: null, like_count: 912, comment_count: 134, created_at: ago(15, 'day') },
]

export const mockComments: Comment[] = [
  { id: 101, post_id: 1, user_id: 2, username: '日更三千', content: '三百章才出山……冲着这句我反而想看了，慢热的都是细糠。', like_count: 89, created_at: ago(1, 'hour') },
  { id: 102, post_id: 1, user_id: 6, username: '咕咕咕咕', content: '已加入书架。如果不好看，我就把你的推书单全埋了（不是', like_count: 45, created_at: ago(2, 'hour') },
  { id: 103, post_id: 2, user_id: 1, username: '夜班书虫', content: '"作者是第一个挨刀的"，这句话我要裱起来。更，都可以更！', like_count: 112, created_at: ago(4, 'hour') },
  { id: 104, post_id: 2, user_id: 7, username: '本章说十级学者', content: '八点零五分了，说好的八点呢？（催更专用语气）', like_count: 156, created_at: ago(4, 'hour') },
  { id: 105, post_id: 3, user_id: 3, username: '毒舌推书君', content: '"把代价写没了"——六个字判了死刑，精准。', like_count: 67, created_at: ago(8, 'hour') },
  { id: 106, post_id: 5, user_id: 2, username: '日更三千', content: '作为作者五味杂陈。写的速度跟不上拍的速度，以后是不是写完直接出片？', like_count: 78, created_at: ago(20, 'hour') },
  { id: 107, post_id: 6, user_id: 1, username: '夜班书虫', content: '"如果没补，当我没说"——这就是你月更三章的理由？', like_count: 203, created_at: ago(1, 'day') },
  { id: 108, post_id: 8, user_id: 4, username: '设定控不打烊', content: '记下了：矛盾、金手指、小高潮。这就去拆我书架里的书对答案。', like_count: 54, created_at: ago(1, 'day') },
  { id: 109, post_id: 13, user_id: 3, username: '毒舌推书君', content: '哈哈哈哈投稿人比你懂你自己系列', like_count: 167, created_at: ago(4, 'day') },
  { id: 110, post_id: 18, user_id: 5, username: '咸鱼编辑', content: '《道诡异仙》有品位。回你一本《深海余烬》，慢热群像，完本保障。', like_count: 43, created_at: ago(8, 'day') },
]

export const mockNotifications: NotificationItem[] = [
  { id: 301, user_id: 1, actor_id: 3, actor_name: '毒舌推书君', type: 'like', resource_id: 4, resource_type: 'post', content: '赞了你的帖子「追了三年的书今天完结了……」', is_read: false, created_at: ago(40, 'minute') },
  { id: 302, user_id: 1, actor_id: 6, actor_name: '咕咕咕咕', type: 'comment', resource_id: 18, resource_type: 'post', content: '评论了你的帖子：我回你一本《高山仰止》，换你的《道诡异仙》', is_read: false, created_at: ago(3, 'hour') },
  { id: 303, user_id: 1, actor_id: 2, actor_name: '日更三千', type: 'follow', resource_id: 2, resource_type: 'user', content: '关注了你', is_read: false, created_at: ago(6, 'hour') },
  { id: 304, user_id: 1, actor_id: 8, actor_name: '漫剧观察员', type: 'like', resource_id: 10, resource_type: 'post', content: '赞了你的帖子「深夜破防时刻：追了八百章的悬疑文……」', is_read: true, created_at: ago(1, 'day') },
  { id: 305, user_id: 1, actor_id: 7, actor_name: '本章说十级学者', type: 'comment', resource_id: 10, resource_type: 'post', content: '评论了你的帖子：猫：是作者让我干的', is_read: true, created_at: ago(2, 'day') },
  { id: 306, user_id: 1, actor_id: 4, actor_name: '设定控不打烊', type: 'like', resource_id: 18, resource_type: 'post', content: '赞了你的帖子「书荒了，来交换书单……」', is_read: true, created_at: ago(3, 'day') },
  { id: 307, user_id: 1, actor_id: 5, actor_name: '咸鱼编辑', type: 'follow', resource_id: 5, resource_type: 'user', content: '关注了你', is_read: true, created_at: ago(5, 'day') },
]

export const mockHotSearches: HotSearch[] = [
  { rank: 1, keyword: '玄鉴仙族 完本', heat: 48200 },
  { rank: 2, keyword: '宿命之环 更新', heat: 41500 },
  { rank: 3, keyword: '求末世文书单', heat: 36900 },
  { rank: 4, keyword: '黄金三章怎么写', heat: 31000 },
  { rank: 5, keyword: 'AI 漫剧改编', heat: 28400 },
  { rank: 6, keyword: '全勤奖', heat: 21000 },
  { rank: 7, keyword: '太监文吐槽大会', heat: 15300 },
  { rank: 8, keyword: '本章说名场面', heat: 12800 },
]

/** 当前登录用户（mock） */
export const CURRENT_USER_ID = 1

/** mock 点赞状态：当前用户已赞的帖子 */
export const mockLikedPostIds = new Set<number>([2, 7, 13])

/** mock 关注关系：当前用户关注的人 */
export const mockFollowingIds = new Set<number>([2, 3, 5])
/** mock 粉丝 */
export const mockFollowerIds = [2, 4, 7]
