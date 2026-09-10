'''
搜索服务业务配置
职责：索引名称、分片策略、银蛇规则等业务相关配置
'''
import os

class SearchConfig:
    '''搜索业务专属配置'''
    #所应前缀
    INDEX_PREFIX:str='weibo'
    
    #索引配置(分片，副本，分词器)
    INDEX_SETTINGS={
        'settings':{
            'number_of_shards':1,
            'number_of_replicas':0,
            'analysis':{
                'analyzer':{
                    'ik_smart':{
                        'type':'custom',
                        'tokenizer':'ik_smart'
                    },
                    'ik_max_word':{
                        'type':'custom',
                        'tokenizer':'ik_max_word'
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