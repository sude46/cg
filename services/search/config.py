'''
搜索服务业务配置
职责：索引名称、分片策略、银蛇规则等业务相关配置
'''

class SearchConfig:
    '''搜索业务专属配置'''
    #所应前缀
    INDEX_PREFIX:str='weibo'

    #索引配置(分片，副本，分词器)
    INDEX_SETTINGS={
        'settings':{
            'number_of_shards':1,
            'number_of_replicas':0,
            # ngram tokenizer 要求 max_gram-min_gram <= 此值，默认仅 1
            'max_ngram_diff':15,
            'analysis':{
                'filter':{
                    # 自动补全用：对 IK 分出的词再切 edge n-gram
                    'edge_ngram_filter':{
                        'type':'edge_ngram',
                        'min_gram':1,
                        'max_gram':10
                    }
                },
                'tokenizer':{
                    # 子串检索用：对原文切 2~15 长度的 n-gram（支持任意"部分内容"）
                    'ngram_tokenizer':{
                        'type':'ngram',
                        'min_gram':2,
                        'max_gram':15,
                        'token_chars':['letter','digit']
                    }
                },
                'analyzer':{
                    'ik_smart':{
                        'type':'custom',
                        'tokenizer':'ik_smart'
                    },
                    'ik_max_word':{
                        'type':'custom',
                        'tokenizer':'ik_max_word'
                    },
                    # 建索引（补全字段）用：IK max_word + 小写 + 前缀 n-gram
                    'ik_edge_ngram':{
                        'type':'custom',
                        'tokenizer':'ik_max_word',
                        'filter':['lowercase','edge_ngram_filter']
                    },
                    # 子串检索字段用：原文 n-gram（不依赖分词成词）
                    'ngram_analyzer':{
                        'type':'custom',
                        'tokenizer':'ngram_tokenizer',
                        'filter':['lowercase']
                    }

                }
            }
        }
    }
    @classmethod
    def init_app(cls,app_config:dict):
        '''从Flask配置初始化'''
        cls.INDEX_PREFIX=app_config.get('ES_INDEX_PREFIX','weibo')

    @classmethod
    def get_index_name(cls,index_type:str):
        '''获取完整索引名'''
        return f'{cls.INDEX_PREFIX}_{index_type}'
